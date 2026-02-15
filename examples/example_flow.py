"""Example showing bae's automatic routing flow."""

from bae import Node, Graph, LM, Dep, Effect
from typing import Annotated


class Start(Node):
    user_input: str = ""
    
    def __call__(self, lm: LM) -> "ProcessInput | End":
        """LM decides: route to ProcessInput or End based on user_input."""
        ...


class ProcessInput(Node):
    processed_data: str = ""
    
    def __call__(self, lm: LM) -> "ValidateData":
        """LM fills processed_data, always routes to ValidateData."""
        ...


class ValidateData(Node):
    is_valid: bool = False
    validation_error: str = ""
    
    def __call__(self, lm: LM) -> "SaveData | RetryInput":
        """LM fills validation fields, then decides routing."""
        ...


def log_save(data: str) -> None:
    """Side effect function for logging."""
    print(f"Saving: {data}")


class SaveData(Node):
    success: bool = False
    
    def __call__(self, lm: LM) -> Annotated["End", Effect(log_save)]:
        """LM fills success field, Effect logs the save."""
        ...


class RetryInput(Node):
    retry_count: int = 0
    
    def __call__(self, lm: LM) -> "Start | End":
        """LM decides: retry (Start) or give up (End)."""
        ...


class End(Node):
    result: str = ""
    
    def __call__(self, lm: LM) -> None:
        """Terminal node - execution stops here."""
        ...


# Usage:
# graph = Graph.from_nodes(Start, ProcessInput, ValidateData, SaveData, RetryInput, End)
# result = await graph.arun(Start(user_input="hello world"), lm)