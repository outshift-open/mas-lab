# MAS-Lab ontology extensions

These TTL files declare native-path KG classes that **PyPI `oxp-ontology` 1.0.0 does not yet ship**. They are not a second ontology.

| Source | Classes |
| --- | --- |
| `oxp-ontology` (PyPI) | Session, MASCall, AgentCall, LLMCall, ToolCall, ProcessingCall, State, Transition, MAS, Agent, LLM, Tool, Processing, Capability, CapabilityCall |
| This directory (pending upstream) | RAGQuery, MemoryCall, SkillCall, Skill, CallAnnotation, ContextContribution, ParallelGroup, Branch, GovernanceEvent, Worker, Run, Application, ThinkingCall |

Remove a class from `mas-kg-native-extensions.ttl` once it lands in oxp-ontology.
