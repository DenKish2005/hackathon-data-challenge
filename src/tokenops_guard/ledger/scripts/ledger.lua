-- All KEYS use one Redis Cluster hash slot. Monetary arithmetic stays below 2^53.
-- Redis TIME is authoritative; worker clock drift cannot extend a lease.
local run, calls, events, leases, progress = unpack(KEYS)
local op = ARGV[1]
local a = cjson.decode(ARGV[2])
local clock = redis.call('TIME')
local now = tonumber(clock[1]) * 1000 + math.floor(tonumber(clock[2]) / 1000)
local function n(field) return tonumber(redis.call('HGET', run, field) or '0') end
local function inc(field, amount) return redis.call('HINCRBY', run, field, amount) end
local function reply(code, extra)
    return cjson.encode({code=code, data=extra or {}})
end
local function event(kind, detail)
    local e = detail or {}
    e.kind = kind
    e.run_id = a.run_id
    e.timestamp = now
    e.total_run_cost = n('spent')
    e.reserved_cost = n('reserved')
    e.remaining_budget = n('budget') - n('spent') - n('reserved')
    e.halt_reason = redis.call('HGET', run, 'halt_reason') or ''
    redis.call('RPUSH', events, cjson.encode(e))
end
local function halt(reason)
    local status = redis.call('HGET', run, 'status')
    -- Never overwrite the first halt reason or silently reopen a terminal run.
    if status == 'RUNNING' or status == 'STEERED' then
        redis.call('HSET', run, 'status', 'HALTED', 'halt_reason', reason)
        inc('revision', 1)
        event('HALT', {policy_triggered=reason})
    end
end
if op == 'create' then
    for _, key in ipairs(KEYS) do
        if redis.call('EXISTS', key) == 1 then return reply('EXISTS') end
    end
    redis.call('HSET', run, 'run_id', a.run_id, 'budget', a.budget,
        'max_tokens', a.max_tokens, 'spent', 0, 'reserved', 0, 'reserved_tokens', 0,
        'input_tokens', 0, 'output_tokens', 0, 'calls', 0, 'steps', 0,
        'active', 0, 'status', 'RUNNING', 'halt_reason', '', 'steered', 0, 'revision', 0,
        'context', a.context, 'settings', a.settings, 'fingerprint', a.fingerprint,
        'admin_hash', a.admin_hash, 'steer_at', a.steer_at)
    event('RUN_CREATED')
    return reply('OK')
end
if redis.call('EXISTS', run) == 0 then return reply('MISSING') end
local settings = cjson.decode(redis.call('HGET', run, 'settings'))
local policies = settings.policies
local function running()
    local s = redis.call('HGET', run, 'status')
    return s == 'RUNNING' or s == 'STEERED'
end
local function authorized() return a.admin_hash == redis.call('HGET', run, 'admin_hash') end
local function steer()
    local guard = policies.cost_guard
    if guard.enabled and n('steered') == 0 and n('spent') >= n('steer_at') then
        redis.call('HSET', run, 'steered', 1)
        if running() then redis.call('HSET', run, 'status', 'STEERED') end
        event('STEER', {policy_triggered='cost_guard', model=settings.model_routing.fallback})
    end
end
local function unknown(id, c, reason)
    if c.state == 'RESERVED' then
        c.state = 'UNKNOWN'
        c.failure = reason
        redis.call('HSET', calls, id, cjson.encode(c))
        redis.call('ZREM', leases, id)
        inc('active', -1)
        inc('revision', 1)
        halt('uncertain_billing')
        event('UNKNOWN', {call_id=id, agent_id=c.agent_id, model=c.model,
            provider=c.provider, estimated_cost=c.cost, policy_triggered=reason})
    end
end
if op == 'preflight' or op == 'reserve' then
    if a.fingerprint ~= redis.call('HGET', run, 'fingerprint') then return reply('CONFIG') end
    if not running() then return reply('HALTED', redis.call('HGET', run, 'halt_reason')) end
    if policies.step_cap.enabled and (n('steps') >= policies.step_cap.max_steps
        or n('calls') >= policies.step_cap.max_calls) then
        halt('step_cap')
        return reply('HALTED', 'step_cap')
    end
    if policies.concurrency_cap.enabled and n('active') >= policies.concurrency_cap.max_parallel_calls then
        return reply('CONCURRENCY')
    end
    if op == 'preflight' then return reply('OK') end
    if redis.call('HEXISTS', calls, a.call_id) == 1 then return reply('DUPLICATE') end
    if n('steered') == 1 and a.model ~= settings.model_routing.fallback then return reply('RETRY') end
    if n('spent') + n('reserved') + a.cost > n('budget')
        or n('input_tokens') + n('output_tokens') + n('reserved_tokens') + a.tokens > n('max_tokens') then
        return reply('RETRY')
    end
    local c = {state='RESERVED', cost=a.cost, tokens=a.tokens, agent_id=a.agent_id,
        model=a.model, provider=a.provider, step_id=a.step_id, trace_id=a.trace_id,
        started_at=now, lease_until=now+a.lease_ms}
    redis.call('HSET', calls, a.call_id, cjson.encode(c))
    redis.call('ZADD', leases, c.lease_until, a.call_id)
    inc('reserved', a.cost)
    inc('reserved_tokens', a.tokens)
    inc('active', 1)
    inc('calls', 1)
    inc('steps', 1)
    inc('revision', 1)
    event('RESERVED', {call_id=a.call_id, agent_id=a.agent_id, model=a.model,
        provider=a.provider, step_id=a.step_id, trace_id=a.trace_id, estimated_cost=a.cost})
    return reply('OK', c)
elseif op == 'halt_if_unchanged' then
    if n('revision') ~= a.revision then return reply('RETRY') end
    halt(a.reason)
    return reply('BUDGET', a.reason)
elseif op == 'halt' then
    halt(a.reason)
    return reply('OK')
elseif op == 'settle' or op == 'resolve' then
    if op == 'resolve' and not authorized() then return reply('AUTH') end
    local raw = redis.call('HGET', calls, a.call_id)
    if not raw then return reply('CALL_MISSING') end
    local c = cjson.decode(raw)
    if c.state == 'SETTLED' then
        if c.actual_cost == a.cost and c.input_tokens == a.input_tokens
            and c.output_tokens == a.output_tokens
            and c.cached_input_tokens == a.cached_input_tokens
            and c.cache_write_input_tokens == a.cache_write_input_tokens then return reply('OK', c) end
        return reply('CONFLICT')
    end
    if n('spent') + a.cost > 9000000000000000 then return reply('ACCOUNTING_OVERFLOW') end
    if c.state == 'RESERVED' then inc('active', -1) end
    inc('reserved', -c.cost)
    inc('reserved_tokens', -c.tokens)
    inc('spent', a.cost)
    inc('input_tokens', a.input_tokens)
    inc('output_tokens', a.output_tokens)
    inc('revision', 1)
    c.state = 'SETTLED'
    c.actual_cost = a.cost
    c.input_tokens = a.input_tokens
    c.output_tokens = a.output_tokens
    c.cached_input_tokens = a.cached_input_tokens
    c.cache_write_input_tokens = a.cache_write_input_tokens
    c.request_id = a.request_id
    c.execution_time_ms = now-c.started_at
    c.evidence = a.evidence
    redis.call('HSET', calls, a.call_id, cjson.encode(c))
    redis.call('ZREM', leases, a.call_id)
    local function attribute(field)
        local totals = cjson.decode(redis.call('HGET', run, field) or '{"spent":0,"input_tokens":0,"output_tokens":0,"calls":0}')
        totals.spent = totals.spent + a.cost
        totals.input_tokens = totals.input_tokens + a.input_tokens
        totals.output_tokens = totals.output_tokens + a.output_tokens
        totals.calls = totals.calls + 1
        redis.call('HSET', run, field, cjson.encode(totals))
    end
    attribute('agent:'..c.agent_id)
    attribute('model:'..c.model)
    local overrun = a.cost > c.cost or a.input_tokens + a.output_tokens > c.tokens
    if overrun then halt('estimate_overrun')
    elseif n('spent') + n('reserved') > n('budget')
        or n('input_tokens')+n('output_tokens')+n('reserved_tokens') > n('max_tokens') then
        halt('budget_overrun')
    elseif n('spent') >= n('budget') then halt('cost_budget')
    elseif n('input_tokens')+n('output_tokens') >= n('max_tokens') then halt('token_budget') end
    steer()
    event(op == 'resolve' and 'RECONCILED' or 'SETTLED', {call_id=a.call_id,
        agent_id=c.agent_id, model=c.model, provider=c.provider, step_id=c.step_id,
        trace_id=c.trace_id, input_tokens=a.input_tokens, output_tokens=a.output_tokens,
        cached_input_tokens=a.cached_input_tokens, cache_write_input_tokens=a.cache_write_input_tokens,
        estimated_cost=c.cost, actual_cost=a.cost, execution_time_ms=c.execution_time_ms,
        estimate_overrun=overrun})
    return reply('OK', c)
elseif op == 'unknown' or op == 'heartbeat' then
    local raw = redis.call('HGET', calls, a.call_id)
    if not raw then return reply('CALL_MISSING') end
    local c = cjson.decode(raw)
    if op == 'unknown' then unknown(a.call_id, c, a.reason)
    elseif c.state == 'RESERVED' then
        if c.lease_until <= now then unknown(a.call_id, c, 'lease_expired')
        else
            c.lease_until = now+a.lease_ms
            redis.call('HSET', calls, a.call_id, cjson.encode(c))
            redis.call('ZADD', leases, c.lease_until, a.call_id)
        end
    end
    return reply('OK', c.state)
elseif op == 'reconcile' then
    local expired = redis.call('ZRANGEBYSCORE', leases, '-inf', now, 'LIMIT', 0, 100)
    for _, id in ipairs(expired) do
        local c = cjson.decode(redis.call('HGET', calls, id))
        unknown(id, c, 'lease_expired')
    end
    return reply('OK', #expired)
elseif op == 'resume' then
    if not authorized() then return reply('AUTH') end
    if redis.call('HGET', run, 'status') ~= 'HALTED' then return reply('HALTED', 'not_halted') end
    -- This primitive intentionally refuses unresolved billing or exhausted budgets/caps.
    if n('reserved') ~= 0 or n('reserved_tokens') ~= 0 or n('active') ~= 0 then return reply('UNRESOLVED') end
    if a.budget < n('budget') or a.max_tokens < n('max_tokens') then return reply('CONFLICT') end
    if n('spent') >= a.budget or n('input_tokens')+n('output_tokens') >= a.max_tokens then
        return reply('BUDGET', 'budget_exhausted')
    end
    if policies.step_cap.enabled and (n('steps') >= policies.step_cap.max_steps
        or n('calls') >= policies.step_cap.max_calls) then return reply('HALTED', 'step_cap_exhausted') end
    redis.call('HSET', run, 'status', n('steered') == 1 and 'STEERED' or 'RUNNING',
        'halt_reason', '', 'budget', a.budget, 'max_tokens', a.max_tokens, 'steer_at', a.steer_at)
    redis.call('DEL', progress)
    inc('revision', 1)
    event('RESUMED', {policy_triggered='operator_resume', evidence=a.evidence})
    return reply('OK')
elseif op == 'progress' then
    if not running() then return reply('HALTED', redis.call('HGET', run, 'halt_reason')) end
    if not policies.progress_guard.enabled then return reply('OK') end
    local guard = policies.progress_guard
    local history = cjson.decode(redis.call('HGET', progress, a.agent_id) or '[]')
    table.insert(history, a.fingerprint)
    local cap = guard.max_repeated_actions * guard.max_pattern_length
    while #history > cap do table.remove(history, 1) end
    redis.call('HSET', progress, a.agent_id, cjson.encode(history))
    local max_repeats = 1
    for width=1,guard.max_pattern_length do
        local repeats = 1
        while (repeats+1)*width <= #history do
            local matches = true
            for j=0,width-1 do
                if history[#history-j] ~= history[#history-repeats*width-j] then matches=false; break end
            end
            if not matches then break end
            repeats = repeats+1
        end
        if repeats > max_repeats then max_repeats=repeats end
    end
    if max_repeats >= guard.max_repeated_actions then
        halt('progress_guard')
        return reply('HALTED', 'progress_guard')
    elseif max_repeats == guard.max_repeated_actions-1 then
        event('PROGRESS_WARNING', {agent_id=a.agent_id, policy_triggered='progress_guard'})
    end
    return reply('OK')
elseif op == 'step' then
    if not running() then return reply('HALTED') end
    if policies.step_cap.enabled and n('steps') >= policies.step_cap.max_steps then
        halt('step_cap'); return reply('HALTED', 'step_cap')
    end
    inc('steps', 1)
    inc('revision', 1)
    event('TOOL_STEP', {agent_id=a.agent_id, step_id=a.step_id})
    return reply('OK')
elseif op == 'finish' then
    if not running() then return reply('HALTED') end
    if n('reserved') ~= 0 or n('reserved_tokens') ~= 0 or n('active') ~= 0 then return reply('UNRESOLVED') end
    redis.call('HSET', run, 'status', a.status)
    inc('revision', 1)
    event(a.status)
    return reply('OK')
elseif op == 'expire' then
    if not authorized() then return reply('AUTH') end
    local s = redis.call('HGET', run, 'status')
    if (s ~= 'COMPLETED' and s ~= 'FAILED') or n('reserved') ~= 0
        or n('reserved_tokens') ~= 0 or n('active') ~= 0 then return reply('UNRESOLVED') end
    event('ARCHIVED')
    for _, key in ipairs(KEYS) do redis.call('EXPIRE', key, a.ttl_s) end
    return reply('OK')
end
return reply('INVALID_OPERATION')
