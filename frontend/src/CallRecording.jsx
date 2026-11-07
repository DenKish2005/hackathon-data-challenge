import React, { useEffect, useRef, useState } from "react";
import { AudioLines, ExternalLink, Headphones, RotateCcw } from "lucide-react";
import "./call-recording.css";

const MAX_AUDIO_BYTES = 25 * 1024 * 1024;
const MAX_WAVEFORM_SECONDS = 30 * 60;
const FETCH_TIMEOUT_MS = 20_000;

function sourceUrl(value) {
  if (typeof value !== "string" || !value.trim()) return null;
  try {
    const url = new URL(value, window.location.href);
    return ["https:", "http:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

function timeLabel(value) {
  const seconds = Number.isFinite(value) ? Math.max(0, Math.floor(value)) : 0;
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

async function boundedAudio(response, signal) {
  if (!response.ok) throw new Error("Источник не отдал аудиофайл.");
  const range = /^bytes (\d+)-(\d+)\/(\d+)$/.exec(
    response.headers.get("Content-Range") || "",
  );
  if (
    range &&
    (Number(range[1]) !== 0 || Number(range[2]) + 1 < Number(range[3]))
  ) {
    await response.body?.cancel();
    throw new Error(
      "Источник передал только часть записи. Полная звуковая дорожка недоступна; используйте аудиоплеер.",
    );
  }
  if (Number(response.headers.get("Content-Length")) > MAX_AUDIO_BYTES) {
    await response.body?.cancel();
    throw new Error("Для построения дорожки доступна запись до 25 МБ.");
  }
  const reader = response.body?.getReader();
  if (!reader)
    throw new Error("Источник не поддерживает загрузку звуковой дорожки.");
  const chunks = [];
  let size = 0;
  try {
    while (true) {
      if (signal.aborted) throw new DOMException("Отменено", "AbortError");
      const { value, done } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_AUDIO_BYTES) {
        await reader.cancel();
        throw new Error("Для построения дорожки доступна запись до 25 МБ.");
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return bytes.buffer;
}

function envelope(buffer) {
  const bars = 160;
  const channels = Array.from(
    { length: buffer.numberOfChannels },
    (_, channel) => buffer.getChannelData(channel),
  );
  const peaks = [];
  for (let bar = 0; bar < bars; bar++) {
    const start = Math.floor((bar / bars) * buffer.length);
    const end = Math.floor(((bar + 1) / bars) * buffer.length);
    let peak = 0;
    // Sample actual PCM points from every source channel. No speaker mapping is inferred.
    const step = Math.max(1, Math.floor((end - start) / 100));
    for (const channel of channels) {
      for (let sample = start; sample < end; sample += step) {
        peak = Math.max(peak, Math.abs(channel[sample]));
      }
    }
    peaks.push(Math.min(1, peak));
  }
  return peaks;
}

export default function CallRecording({
  audioUrl,
  dialogId,
  imported = false,
}) {
  const source = sourceUrl(audioUrl);
  // Organizer links are HTML players; the backend resolves and streams their real audio.
  const url =
    source && imported && dialogId
      ? `/api/conversations/${encodeURIComponent(dialogId)}/audio`
      : source;
  const player = useRef(null);
  const request = useRef(null);
  const generation = useRef(0);
  const [audioError, setAudioError] = useState(false);
  const [waveError, setWaveError] = useState("");
  const [wave, setWave] = useState(null);
  const [loading, setLoading] = useState(false);
  const [duration, setDuration] = useState(0);
  const [position, setPosition] = useState(0);

  useEffect(() => {
    generation.current += 1;
    request.current?.abort();
    setAudioError(false);
    setWaveError("");
    setWave(null);
    setLoading(false);
    setDuration(0);
    setPosition(0);
    return () => {
      generation.current += 1;
      request.current?.abort();
    };
  }, [url, dialogId]);

  async function loadWaveform() {
    if (!url || loading) return;
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) {
      setWaveError("Браузер не поддерживает дорожку. Используйте аудиоплеер.");
      return;
    }
    const metadataDuration = player.current?.duration;
    if (!Number.isFinite(metadataDuration) || metadataDuration <= 0) {
      setWaveError(
        "Дождитесь загрузки записи в плеере, затем покажите дорожку.",
      );
      return;
    }
    if (metadataDuration > MAX_WAVEFORM_SECONDS) {
      setWaveError(
        "Для длинной записи используйте плеер: дорожка доступна до 30 минут.",
      );
      return;
    }
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    const currentGeneration = generation.current;
    const current = () =>
      generation.current === currentGeneration &&
      request.current === controller;
    let context;
    let timeoutReached = false;
    let removeAbort = () => {};
    const timer = setTimeout(() => {
      timeoutReached = true;
      controller.abort();
    }, FETCH_TIMEOUT_MS);
    setLoading(true);
    setWaveError("");
    try {
      const response = await fetch(url, {
        signal: controller.signal,
        credentials: "same-origin",
      });
      const bytes = await boundedAudio(response, controller.signal);
      if (!current()) return;
      context = new AudioContext();
      const cancelled = new Promise((_, reject) => {
        const abort = () => reject(new DOMException("Отменено", "AbortError"));
        controller.signal.addEventListener("abort", abort, { once: true });
        removeAbort = () =>
          controller.signal.removeEventListener("abort", abort);
        if (controller.signal.aborted) abort();
      });
      const decoded = await Promise.race([
        context.decodeAudioData(bytes),
        cancelled,
      ]);
      if (!current()) return;
      if (decoded.duration > MAX_WAVEFORM_SECONDS) {
        throw new Error(
          "Для длинной записи используйте плеер: дорожка доступна до 30 минут.",
        );
      }
      setWave({
        peaks: envelope(decoded),
        duration: decoded.duration,
        channels: decoded.numberOfChannels,
      });
    } catch (error) {
      if (current()) {
        setWaveError(
          timeoutReached
            ? "Источник долго отвечает. Аудиоплеер остаётся доступен; попробуйте дорожку позже."
            : error.name === "AbortError"
              ? "Построение дорожки отменено."
              : error.message.includes("25 МБ") ||
                  error.message.includes("30 минут") ||
                  error.message.includes("часть записи")
                ? error.message
                : "Не удалось построить дорожку: источник может ограничивать загрузку (CORS). Аудиоплеер работает отдельно.",
        );
      }
    } finally {
      clearTimeout(timer);
      removeAbort();
      if (context) await context.close().catch(() => {});
      if (current()) setLoading(false);
    }
  }

  function seek(seconds) {
    const audio = player.current;
    if (!audio || !Number.isFinite(audio.duration) || audio.duration <= 0)
      return;
    const next = Math.max(0, Math.min(seconds, audio.duration));
    audio.currentTime = next;
    setPosition(next);
  }

  return (
    <section className="call-recording" aria-label="Запись разговора">
      <div className="call-recording-heading">
        <div>
          <Headphones size={17} />
          <h2>Запись разговора</h2>
          <span>{url ? "Аудиофайл из данных диалога" : "Без аудиофайла"}</span>
        </div>
        {url && (
          <a href={url} target="_blank" rel="noreferrer">
            Открыть запись <ExternalLink size={12} />
          </a>
        )}
      </div>
      {!url ? (
        <p className="call-recording-empty">
          К диалогу не приложена аудиозапись. Ниже доступна расшифровка.
        </p>
      ) : (
        <>
          <audio
            key={`${dialogId || "call"}:${url}`}
            ref={player}
            className="call-recording-player"
            controls
            preload="metadata"
            src={url}
            aria-label={`Аудиозапись диалога ${dialogId || ""}`.trim()}
            onLoadedMetadata={(event) => {
              const value = event.currentTarget.duration;
              setDuration(Number.isFinite(value) ? value : 0);
              setAudioError(false);
            }}
            onTimeUpdate={(event) =>
              setPosition(event.currentTarget.currentTime)
            }
            onError={() => setAudioError(true)}
          />
          {audioError && (
            <div className="call-recording-error" role="status">
              <p>
                Запись не загрузилась. Ссылка могла истечь или источник
                недоступен. Попробуйте снова или откройте запись отдельно.
              </p>
              <button
                onClick={() => {
                  setAudioError(false);
                  player.current?.load();
                }}
              >
                <RotateCcw size={13} /> Повторить загрузку
              </button>
            </div>
          )}
          {wave ? (
            <div className="call-recording-waveform">
              <svg
                className="call-recording-wave"
                viewBox="0 0 960 64"
                preserveAspectRatio="none"
                role="slider"
                tabIndex={0}
                aria-label="Позиция в аудиозаписи"
                aria-valuemin={0}
                aria-valuemax={duration || wave.duration}
                aria-valuenow={position}
                aria-valuetext={`${timeLabel(position)} из ${timeLabel(duration || wave.duration)}`}
                onClick={(event) => {
                  const bounds = event.currentTarget.getBoundingClientRect();
                  seek(
                    ((event.clientX - bounds.left) / bounds.width) *
                      (duration || wave.duration),
                  );
                }}
                onKeyDown={(event) => {
                  const actions = {
                    ArrowLeft: position - 5,
                    ArrowRight: position + 5,
                    Home: 0,
                    End: duration || wave.duration,
                  };
                  if (Object.hasOwn(actions, event.key)) {
                    event.preventDefault();
                    seek(actions[event.key]);
                  }
                }}
              >
                <line
                  x1="0"
                  y1="32"
                  x2="960"
                  y2="32"
                  className="call-recording-baseline"
                />
                {wave.peaks.map((peak, index) => {
                  const height = peak * 54;
                  return (
                    <rect
                      key={index}
                      x={index * 6 + 1}
                      y={32 - height / 2}
                      width="3"
                      height={height}
                      rx="1"
                      className={
                        (index / wave.peaks.length) * wave.duration <= position
                          ? "is-played"
                          : ""
                      }
                    />
                  );
                })}
                <line
                  x1={Math.min(960, (position / wave.duration) * 960)}
                  x2={Math.min(960, (position / wave.duration) * 960)}
                  y1="2"
                  y2="62"
                  className="call-recording-playhead"
                />
              </svg>
              <div className="call-recording-wave-caption">
                <span>
                  Амплитуда записи
                  {wave.channels > 1 ? " · каналы объединены" : ""}
                </span>
                <time>
                  {timeLabel(position)} / {timeLabel(duration || wave.duration)}
                </time>
              </div>
            </div>
          ) : (
            <div className="call-recording-wave-action">
              <button disabled={loading} onClick={loadWaveform}>
                <AudioLines size={14} />
                {loading ? "Строится дорожка…" : "Показать звуковую дорожку"}
              </button>
              <span>По реальному аудио · до 25 МБ</span>
            </div>
          )}
          {waveError && (
            <p className="call-recording-wave-error" role="status">
              {waveError}
            </p>
          )}
        </>
      )}
    </section>
  );
}
