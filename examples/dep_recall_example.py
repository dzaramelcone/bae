"""Example showing Dep (dependency injection) and Recall patterns."""

from bae import Node, Graph, LM, Dep, Recall
from typing import Annotated
import datetime


# Dependency functions
def get_current_time() -> str:
    return datetime.datetime.now().isoformat()

def get_user_session() -> str:
    return "session_12345"

def confirm_action(action: str) -> bool:
    """User gate function - LM routes based on this bool result."""
    print(f"Confirm: {action}? (y/n)")
    return input().lower().startswith('y')


class StartSession(Node):
    # Deps are injected automatically before execution
    timestamp: Annotated[str, Dep(get_current_time)]
    session_id: Annotated[str, Dep(get_user_session)]
    user_request: str = ""
    
    def __call__(self, lm: LM) -> "AnalyzeRequest":
        """LM fills user_request, always routes to analysis."""
        ...


class AnalyzeRequest(Node):
    # Recall finds the StartSession instance in the trace
    original_session: Annotated[StartSession, Recall()]
    analysis: str = ""
    risk_level: str = ""  # "low", "medium", "high"
    
    def __call__(self, lm: LM) -> "ExecuteAction | RequireConfirmation":
        """LM fills analysis/risk_level, then decides routing."""
        ...


class RequireConfirmation(Node):
    # Recall gets the analysis from previous node
    previous_analysis: Annotated[str, Recall()]  
    # Dep function acts as user gate - LM routes on the bool result
    user_confirmed: Annotated[bool, Dep(lambda: confirm_action("dangerous action"))]
    
    def __call__(self, lm: LM) -> "ExecuteAction | RejectAction":
        """LM routes based on user_confirmed boolean."""
        ...


class ExecuteAction(Node):
    # Recall gets the original session info
    session_info: Annotated[StartSession, Recall()]
    result: str = ""
    
    def __call__(self, lm: LM) -> "LogResult":
        """LM fills result field."""
        ...


class RejectAction(Node):
    reason: str = ""
    
    def __call__(self, lm: LM) -> "LogResult":
        """LM fills rejection reason."""
        ...


class LogResult(Node):
    # Multiple recalls - gets the most recent of each type
    session: Annotated[StartSession, Recall()]
    final_action: Annotated[str, Recall()]  # from ExecuteAction.result or RejectAction.reason
    log_entry: str = ""
    
    def __call__(self, lm: LM) -> None:
        """Terminal node - LM fills log_entry."""
        ...


# Key insights:
# 1. Dep functions run BEFORE the node executes
# 2. User gates → confirmation Dep functions, LM routes on the bool
# 3. Recall finds the most recent matching type in the trace
# 4. Side effects → separate Dep functions where possible