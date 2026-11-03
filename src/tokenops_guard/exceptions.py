class GovernanceError(Exception):
    """Base for safe, non-sensitive governance errors."""


class RunHaltedError(GovernanceError):
    pass


class BudgetExceededError(RunHaltedError):
    pass


class ConcurrencyLimitError(GovernanceError):
    pass


class BudgetStoreUnavailableError(GovernanceError):
    pass


class DuplicateCallError(GovernanceError):
    pass


class SettlementConflictError(GovernanceError):
    pass


class AuthorizationError(GovernanceError):
    pass


class ConfigurationMismatchError(GovernanceError):
    pass


class ProviderNotDispatchedError(GovernanceError):
    """Adapter guarantees the request was not sent; safe to release reservation."""
