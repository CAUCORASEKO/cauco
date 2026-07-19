from cauco_tools.builtin.common import operation, permission
from cauco_tools.models import ToolCategory, ToolDefinition

OLLAMA_TOOL = ToolDefinition(
    id="ollama",
    display_name="Ollama",
    description="Local model capability contracts.",
    category=ToolCategory.MODEL,
    version="1.0.0",
    enabled=True,
    operations=(
        operation("list_models", "List configured local models."),
        operation("generate", "Generate a local model response.", confirmation=True),
    ),
    permissions=(
        permission("model_read", "Inspect local model metadata."),
        permission("model_generate", "Request local model inference."),
    ),
    requires_confirmation=True,
)
