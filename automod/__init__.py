"""Extensible AutoMod rule validation and evaluation."""

from .engine import AutoModEngine, MessageContext, RuleMatch
from .models import ACTION_TYPES, EVENT_TYPES, RATE_TRIGGERS, RULE_FAMILIES, TRIGGER_TYPES, default_rule, validate_rule

__all__ = ["ACTION_TYPES", "EVENT_TYPES", "RATE_TRIGGERS", "RULE_FAMILIES", "TRIGGER_TYPES", "AutoModEngine", "MessageContext", "RuleMatch", "default_rule", "validate_rule"]
