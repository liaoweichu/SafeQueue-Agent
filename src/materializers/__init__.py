"""Source-to-prompt materializers for G2 minimal falsification profiling.

Each materializer reads a frozen source archive and produces the fields
required by the verifier prompt template (verifier-v1.txt):
  state_summary, user_intent, tool_name, tool_arguments, hard_required.
"""

from src.materializers.base import MaterializedRecord, PromptRenderer
from src.materializers.tau_bench import TauBenchMaterializer
from src.materializers.safetoolbench import SafeToolBenchMaterializer
from src.materializers.agentdojo import AgentDojoMaterializer

__all__ = [
    "MaterializedRecord",
    "PromptRenderer",
    "TauBenchMaterializer",
    "SafeToolBenchMaterializer",
    "AgentDojoMaterializer",
]
