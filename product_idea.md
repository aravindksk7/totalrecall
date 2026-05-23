Product: totalrecall

Status note: This original product idea has been superseded by the canonical documents under `docs/`. The accepted build decisions are: Python 3.14+ only for the backend/orchestration runtime; TypeScript only for the admin UI and Playwright-native workers; `uv` for Python package and lock management; local Postgres as the TotalRecall governance store; early AuthProvider, TenantContext, and RBAC from the first APIs; controlled continuous repository learning; in-process Mem0 wrapper for MVP with standalone microservice packaging deferred; config-backed FeatureFlagProvider; environment/local-secret-backed CredentialProvider; StubProvider for deterministic tests; and OpenAIProvider as the first real cloud LLM adapter.

Part 1: Product Requirements Document (PRD)
1.1 Executive Summary
Modern AI test generation engines suffer from token inflation and contextual drift. When a user requests a software test, standard LLM applications pass excessive codebase files or documentation, inflating costs and hitting model context limits. Furthermore, when applications change, models fail to adapt because they lack long-term memory.
The Context-Driven Test Architect (CDTA) is a middleware wrapper layer built on top of Mem0 (long-term memory) and a decoupled Modular Skill Registry. It dynamically manages software architecture contexts, automates modular test framework creation, saves up to 80% on prompt token overhead, and remains completely LLM platform-agnostic.
1.2 User Personas
SDET / QA Automation Engineer: Wants to generate robust, framework-compliant, modular test scripts across Python, Java, or Playwright using clean Page Object Models (POM).
QA Manager / Lead: Demands visibility into what the AI "knows" about their application, with the explicit power to audit, modify, or erase obsolete structural knowledge.
CI/CD DevOps Agent: An autonomous software worker that triggers headless regression test updates, catches broken locators, and requests automatic locator healing updates.
1.3 Functional Requirements
Core Generation & Framework Support
FR-1.1: Must output native, valid test code for Python (Pytest), Java (TestNG/JUnit), and Playwright (TypeScript/JavaScript).
FR-1.2: Must enforce strict modularity using the Page Object Model (POM) design pattern or equivalent depending on tech stack.
FR-1.3: Must dynamically handle locator mapping profiles using a configurable routing mechanism (In-File parameters vs. Central Database queries).
Memory & Token Optimization
FR-2.1: Must parse user prompts to isolate target domains and drop redundant system data before reaching the LLM gateway.
FR-2.2: Must interface with Mem0 to manage dynamic application states, historical element paths, and past UI changes.
FR-2.3: Must maintain a local Skill Registry tracking framework-specific layouts to prevent sending structural tutorials down the LLM context pipeline.
Catalogue Auditing & Unlearning Life Cycle
FR-3.1: Must expose an indexable cataloguing ledger outlining every active system skill and learned dynamic memory component.
FR-3.2: Must allow human operators or autonomous scripts to target and unlearn (permanently delete) specific memory entries via unique IDs.
FR-3.3: Unlearning an entity must immediately invalidate it from the active generation pipeline, preventing dead code generation.
1.4 Non-Functional Requirements
NFR-1 (Agnostic Design): System must run across cloud LLMs (Claude, Gemini, OpenAI) and local models (Llama 3 via Ollama) interchangeably using unified API schemas.
NFR-2 (Latency Optimization): Context resolution and template compilation must complete within 

 prior to dispatching to the target LLM.
NFR-3 (Extensibility): Adding a new target technology framework must require writing a single JSON layout schema without altering core middleware routing code.
Part 2: Technical Design Document (TDD)
2.1 Architecture Overview
                      ┌─────────────────────────────────┐
                      │    User Interface / CI Trigger  │
                      └────────────────┬────────────────┘
                                       │ (Prompt + Config)
                                       ▼
 ┌─────────────────────────────────────────────────────────────────────────────┐
 │                           CDTA WRAPPER CORE                                 │
 │                                                                             │
 │  ┌────────────────────────┐                  ┌───────────────────────────┐  │
 │  │   Metadata Extractor   │                  │   Skill & Memory Router   │  │
 │  └───────────┬────────────┘                  └─────────────┬─────────────┘  │
 │              │                                             │                │
 │              ▼                                             ▼                │
 │  ┌────────────────────────┐                  ┌───────────────────────────┐  │
 │  │  Mem0 Context Adapter  │                  │   Modular Skill Registry  │  │
 │  └───────────┬────────────┘                  └─────────────┬─────────────┘  │
 │              │                                             │                │
 │              └──────────────────────┬──────────────────────┘                │
 │                                     │ (Token-Minimized Payload)             │
 │                                     ▼                                       │
 │                      ┌───────────────────────────────┐                      │
 │                      │  Platform-Agnostic Gateway   │                      │
 │                      └──────────────┬────────────────┘                      │
 └─────────────────────────────────────┼───────────────────────────────────────┘
                                       │ (Unified Routing API)
                                       ▼
                 ┌─────────────────────┼─────────────────────┐
                 ▼                     ▼                     ▼
         ┌───────────────┐     ┌───────────────┐     ┌───────────────┐
         │ Anthropic API │     │  Google API   │     │  Ollama Local │
         └───────────────┘     └───────────────┘     └───────────────┘
2.2 Data Models & Schema Design
2.2.1 Skill Registry Schema (skills_schema.json)
Defines the architectural syntax templates for each tech stack. This avoids passing layout syntax examples inside user prompts.
json
{
  "$schema": "http://json-schema.org",
  "title": "AutomationSkill",
  "type": "object",
  "properties": {
    "skill_id": { "type": "string" },
    "language": { "type": "string", "enum": ["python", "java", "typescript"] },
    "framework": { "type": "string", "enum": ["pytest", "testng", "playwright"] },
    "pattern": { "type": "string", "default": "POM" },
    "template_blueprint": { "type": "string" }
  },
  "required": ["skill_id", "language", "framework", "template_blueprint"]
}
Use code with caution.
2.2.2 Unified Catalogue Ledger Object
The canonical entity structure returned when auditing or filtering the long-term context memory.
json
{
  "entity_id": "mem_01J8Y5B4_X92",
  "category": "dynamic_memory",
  "meta_tags": {
    "domain": "authentication",
    "framework": "playwright",
    "page_route": "/login"
  },
  "extracted_knowledge": "Submit button uses dynamic selector: button[type='submit']",
  "tokens_saved_estimate": 280,
  "created_at": "2026-05-21T07:49:00Z"
}
Use code with caution.
2.3 System Core Pipelines
2.3.1 Token Optimization Engine Pipeline
[Input Request] ──> [Extract Tech Stack & Domain]
                        │
                        ├─> Fetch Skill Template (Deterministic / 0 Tokens)
                        └─> Fetch Mem0 Elements  (Targeted Semantic Search)
                                │
                                ▼
                       [Prompt Synthesizer]
                                │ (Inject Constraints)
                                ▼
                       [Minimalist LLM Payload]
2.3.2 Memory Erasure (Unlearning) Flow
[Delete Request] ──> [Verify Category Type]
                          │
                          ├──> "dynamic_memory" ──> Execute Mem0.delete(entity_id)
                          └──> "static_skill"   ──> Purge local file / DB record
                                │
                                ▼
                       [Invalidate Target Cache] ──> [Return 200 OK Status]
2.4 Low-Level Implementation (Core Middleware Python Script)
This production-grade script structures the entire platform-agnostic middleware logic, including token optimization prompts and catalogue unlearning APIs.
python
import os
import json
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

# Mocking internal infrastructure configurations
class TechStackConfig(BaseModel):
    language: str = Field(..., description="Target language: python, java, or typescript")
    framework: str = Field(..., description="Target framework: pytest, testng, or playwright")
    locator_strategy: str = Field("FILE", description="FILE or DATABASE storage strategy")

class GenerationPayload(BaseModel):
    user_prompt: str
    config: TechStackConfig
    domain_scope: str

class UnlearnPayload(BaseModel):
    entity_id: str
    category: str  # "static_skill" or "dynamic_memory"

class MockMem0Client:
    """Interfacing framework wrapper to simulate actual Mem0 functionalities."""
    def __init__(self):
        self.db = {
            "mem_01_login_user": {
                "entity_id": "mem_01_login_user",
                "domain": "authentication",
                "knowledge": "Username text box selector is '#txt-username'"
            },
            "mem_02_login_pass": {
                "entity_id": "mem_02_login_pass",
                "domain": "authentication",
                "knowledge": "Password text box selector is 'input[type=\"password\"]'"
            }
        }
    
    def search(self, query: str, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        # Filter memories using domain scope parameters to conserve context space
        return [v for k, v in self.db.items() if v["domain"] == filters.get("domain")]
    
    def delete_memory(self, memory_id: str) -> bool:
        if memory_id in self.db:
            del self.db[memory_id]
            return True
        return False

class SkillRegistry:
    """Provides modular syntax patterns without invoking expensive LLM processing blocks."""
    @staticmethod
    def get_skeleton(framework: str) -> str:
        skills = {
            "playwright": (
                "import { Page, Locator } from '@playwright/test';\n"
                "export class BasePage {\n"
                "  constructor(protected page: Page) {}\n"
                "  // {{LOCATOR_ZONE}}\n"
                "}"
            ),
            "pytest": (
                "import pytest\n"
                "class TestBaseAutomation:\n"
                "    # {{LOCATOR_ZONE}}\n"
                "    def setup_method(self):\n"
                "        pass"
            )
        }
        return skills.get(framework.lower(), "// Generic Automation Skeleton Matrix Base")

class PlatformAgnosticOrchestrator:
    def __init__(self):
        self.memory_layer = MockMem0Client()
        self.registry = SkillRegistry()

    def compile_optimized_prompt(self, payload: GenerationPayload) -> Dict[str, Any]:
        # 1. Fetch framework requirements deterministically (Zero Token LLM footprint)
        skeleton_blueprint = self.registry.get_skeleton(payload.config.framework)
        
        # 2. Query Memory Layer using targeted domain filters
        isolated_memories = self.memory_layer.search(
            query=payload.user_prompt, 
            filters={"domain": payload.domain_scope}
        )
        
        memory_context_string = "\n".join([f"- {m['knowledge']}" for m in isolated_memories])
        
        # 3. Formulate the highly constrained token-efficient prompt payload
        system_instruction = (
            "You are a test code generation compiler. Output functional code blocks.\n"
            f"Adhere strictly to this modular code architecture layout:\n{skeleton_blueprint}\n"
            "Do not supply conversational introductions, markdown explanations, or text commentary."
        )
        
        user_refined_execution = (
            f"Task: {payload.user_prompt}\n"
            f"Use exclusively these verified functional elements discovered from system memory:\n"
            f"{memory_context_string}\n"
            f"Locator Strategy Selected: {payload.config.locator_strategy}"
        )
        
        # Ready to drop straight into LiteLLM, Claude, Gemini, or local Ollama gateways
        return {
            "target_model_config": {
                "provider_env_var": "LLM_PROVIDER_TARGET",
                "fallback_sequence": ["claude-3-5-sonnet", "gemini-1.5-pro", "llama3"]
            },
            "payload": {
                "system_prompt": system_instruction,
                "user_prompt": user_refined_execution
            }
        }

    def process_unlearn_command(self, payload: UnlearnPayload) -> Dict[str, Any]:
        if payload.category == "dynamic_memory":
            success = self.memory_layer.delete_memory(payload.entity_id)
            if not success:
                return {"status": "error", "message": f"Entity {payload.entity_id} missing from memory map."}
            return {"status": "success", "message": f"Wiped entity {payload.entity_id} from long-term memory."}
        else:
            return {"status": "skipped", "message": "Static rule structures require registry code modifications."}

# Verification Routine Block
if __name__ == "__main__":
    orchestrator = PlatformAgnosticOrchestrator()
    
    # Simulate a run generating code for Playwright
    job = GenerationPayload(
        user_prompt="Build login validation suite",
        config=TechStackConfig(language="typescript", framework="playwright", locator_strategy="FILE"),
        domain_scope="authentication"
    )
    
    compiled_result = orchestrator.compile_optimized_prompt(job)
    print("=== COMPILED TOKEN-EFFICIENT PROMPT ===")
    print(json.dumps(compiled_result, indent=2))
    
    # Simulate unlearning a piece of outdated historical contextual metadata
    print("\n=== EXECUTING SYSTEM UNLEARN TASK ===")
    unlearn_job = UnlearnPayload(entity_id="mem_01_login_user", category="dynamic_memory")
    unlearn_result = orchestrator.process_unlearn_command(unlearn_job)
    print(json.dumps(unlearn_result, indent=2))
