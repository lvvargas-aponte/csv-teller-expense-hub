"""Schema sanity for Fin agent tool arguments.

The Pydantic models in ``agent.schemas`` are the source of truth for the
JSON schemas the harness sends to Ollama. If the schema shape ever drifts
from what Ollama expects (e.g. missing ``type: object``, missing
``properties``), tool calling silently regresses on local models. These
tests pin the shape and exercise bounds / enum validation.
"""
import pytest
from pydantic import ValidationError

from agent.schemas import (
    GetBalanceArgs,
    GetBudgetStatusArgs,
    GetCategorySpendingArgs,
    GetDebtArgs,
    GetGoalStatusArgs,
    GetInvestmentsArgs,
    ProjectCashflowArgs,
    RecallAboutUserArgs,
    RecallPastConversationArgs,
    RememberAboutUserArgs,
    SearchDocumentsArgs,
    SearchTransactionsArgs,
)
from agent.tools import default_tool_registry


_ALL_MODELS = [
    SearchTransactionsArgs, GetBalanceArgs, GetDebtArgs,
    GetBudgetStatusArgs, GetGoalStatusArgs, ProjectCashflowArgs,
    GetCategorySpendingArgs, GetInvestmentsArgs,
    SearchDocumentsArgs, RecallPastConversationArgs,
    RememberAboutUserArgs, RecallAboutUserArgs,
]


class TestJsonSchemaShape:
    @pytest.mark.parametrize("model", _ALL_MODELS)
    def test_schema_is_object_with_properties(self, model):
        schema = model.model_json_schema()
        assert schema.get("type") == "object"
        assert isinstance(schema.get("properties"), dict)
        # Ollama relies on properties having at least name + type per field.
        for prop_name, prop in schema["properties"].items():
            assert prop_name
            # Either a plain "type" or a union (anyOf) for Optional[...] fields.
            assert "type" in prop or "anyOf" in prop, (
                f"{model.__name__}.{prop_name} missing type/anyOf in schema"
            )

    def test_required_arrays_match_non_default_fields(self):
        # SearchTransactionsArgs requires `query`; everything else is optional.
        schema = SearchTransactionsArgs.model_json_schema()
        assert schema.get("required") == ["query"]

        # AddArgs etc. — verify each model's required list is exactly the set
        # of fields without defaults.
        for model in _ALL_MODELS:
            schema = model.model_json_schema()
            required = set(schema.get("required") or [])
            non_default = {
                name for name, field in model.model_fields.items()
                if field.is_required()
            }
            assert required == non_default, (
                f"{model.__name__}: schema required={required} vs fields={non_default}"
            )

    def test_registry_exposes_clean_openai_shape(self):
        """The registry strips pydantic `title` keys for a tighter prompt."""
        reg = default_tool_registry()
        for tool in reg.openai_tools():
            params = tool["function"]["parameters"]
            assert "title" not in params, "top-level title should be stripped"
            for prop in params["properties"].values():
                assert "title" not in prop, "per-property title should be stripped"


# ---------------------------------------------------------------------------
# Bounds & enums — what the harness's pre-execution validation will reject
# ---------------------------------------------------------------------------

class TestBoundsAndEnums:
    def test_get_balance_account_type_enum(self):
        # Valid values
        for v in ("cash", "credit", "investment", "all"):
            GetBalanceArgs(account_type=v)
        # Invalid
        with pytest.raises(ValidationError):
            GetBalanceArgs(account_type="checking")
        with pytest.raises(ValidationError):
            GetBalanceArgs(account_type="")

    def test_get_balance_defaults_to_all(self):
        assert GetBalanceArgs().account_type == "all"

    def test_project_cashflow_horizon_bounds(self):
        # In-range
        for h in (1, 30, 180):
            assert ProjectCashflowArgs(horizon_days=h).horizon_days == h
        # Out-of-range
        with pytest.raises(ValidationError):
            ProjectCashflowArgs(horizon_days=0)
        with pytest.raises(ValidationError):
            ProjectCashflowArgs(horizon_days=181)
        with pytest.raises(ValidationError):
            ProjectCashflowArgs(horizon_days=-5)

    def test_project_cashflow_default_horizon(self):
        assert ProjectCashflowArgs().horizon_days == 30

    def test_search_transactions_limit_bounds(self):
        # In-range
        for k in (1, 5, 20):
            assert SearchTransactionsArgs(query="x", limit=k).limit == k
        # Out-of-range
        with pytest.raises(ValidationError):
            SearchTransactionsArgs(query="x", limit=0)
        with pytest.raises(ValidationError):
            SearchTransactionsArgs(query="x", limit=21)

    def test_search_transactions_query_required(self):
        with pytest.raises(ValidationError):
            SearchTransactionsArgs()  # type: ignore[call-arg]

    def test_search_transactions_optional_fields_default_none(self):
        a = SearchTransactionsArgs(query="x")
        assert a.category is None
        assert a.start_date is None
        assert a.end_date is None

    def test_get_debt_account_name_optional(self):
        assert GetDebtArgs().account_name is None
        assert GetDebtArgs(account_name="chase").account_name == "chase"

    def test_get_budget_status_category_optional(self):
        assert GetBudgetStatusArgs().category is None

    def test_get_goal_status_goal_id_optional(self):
        assert GetGoalStatusArgs().goal_id is None

    def test_remember_about_user_category_enum(self):
        for cat in ("preference", "constraint", "goal", "life_event", "pattern"):
            RememberAboutUserArgs(fact="x", category=cat)
        with pytest.raises(ValidationError):
            RememberAboutUserArgs(fact="x", category="bogus")

    def test_remember_about_user_fact_required(self):
        with pytest.raises(ValidationError):
            RememberAboutUserArgs(category="goal")  # type: ignore[call-arg]

    def test_remember_about_user_defaults(self):
        a = RememberAboutUserArgs(fact="x", category="goal")
        assert a.tags == []
        assert a.sensitive is False

    def test_recall_about_user_limit_bounds(self):
        for k in (1, 5, 20):
            assert RecallAboutUserArgs(query="x", limit=k).limit == k
        with pytest.raises(ValidationError):
            RecallAboutUserArgs(query="x", limit=0)
        with pytest.raises(ValidationError):
            RecallAboutUserArgs(query="x", limit=21)

    def test_recall_about_user_category_optional(self):
        assert RecallAboutUserArgs(query="x").category is None
        with pytest.raises(ValidationError):
            RecallAboutUserArgs(query="x", category="bogus")

    def test_search_documents_query_required(self):
        with pytest.raises(ValidationError):
            SearchDocumentsArgs()  # type: ignore[call-arg]

    def test_search_documents_limit_bounds(self):
        for k in (1, 4, 10):
            assert SearchDocumentsArgs(query="x", limit=k).limit == k
        with pytest.raises(ValidationError):
            SearchDocumentsArgs(query="x", limit=0)
        with pytest.raises(ValidationError):
            SearchDocumentsArgs(query="x", limit=11)

    def test_search_documents_defaults(self):
        a = SearchDocumentsArgs(query="x")
        assert a.scope is None
        assert a.category is None
        assert a.limit == 4

    def test_recall_past_conversation_limit_bounds(self):
        for k in (1, 5, 20):
            assert RecallPastConversationArgs(query="x", limit=k).limit == k
        with pytest.raises(ValidationError):
            RecallPastConversationArgs(query="x", limit=0)
        with pytest.raises(ValidationError):
            RecallPastConversationArgs(query="x", limit=21)
