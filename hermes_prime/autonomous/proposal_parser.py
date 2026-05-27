from __future__ import annotations

import json
import re
from typing import Any

from hermes_prime.contracts import ActionProposal, ActionType, RiskTier
from hermes_prime.utils import new_urn_uuid, utc_now_iso


class ProposalParsingError(Exception):
    """Raised when LLM output cannot be parsed as ActionProposal."""

    pass


class ProposalParser:
    """Parses LLM-generated text into structured ActionProposal objects."""

    @staticmethod
    def extract_json_block(text: str) -> dict[str, Any]:
        """Extract JSON block from LLM response, handling markdown fences."""
        # Try to find ```json ... ``` block
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            json_str = match.group(1)
        else:
            # Try to find raw JSON object
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                json_str = match.group(0)
            else:
                raise ProposalParsingError(f"No JSON block found in LLM output: {text}")

        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ProposalParsingError(f"Invalid JSON in LLM output: {e}")

    @staticmethod
    def parse(
        llm_output: str,
        intent_root_id: str,
        workspace_root: str,
    ) -> ActionProposal:
        """Parse LLM output into ActionProposal."""
        try:
            proposal_dict = ProposalParser.extract_json_block(llm_output)
        except ProposalParsingError as e:
            raise ProposalParsingError(f"Failed to parse LLM proposal: {e}")

        # Validate required fields
        required_fields = ["action_type", "scope", "capability"]
        missing = [f for f in required_fields if f not in proposal_dict]
        if missing:
            raise ProposalParsingError(f"Missing required fields: {missing}")

        # Normalize and validate action_type
        try:
            action_type = ActionType(proposal_dict["action_type"])
        except ValueError:
            raise ProposalParsingError(f"Invalid action_type: {proposal_dict['action_type']}")

        # Default risk tier to T1 if not specified
        risk_tier_str = proposal_dict.get("risk_tier", "T1")
        try:
            risk_tier = RiskTier(risk_tier_str)
        except ValueError:
            risk_tier = RiskTier.T1

        # Build ActionProposal
        proposal = ActionProposal(
            action_id=new_urn_uuid(),
            action_type=action_type,
            scope=proposal_dict["scope"],
            risk_tier=risk_tier,
            intent_root=intent_root_id,
            capability=proposal_dict["capability"],
            proposed_at=utc_now_iso(),
            parameters=proposal_dict.get("parameters", {}),
        )

        return proposal
