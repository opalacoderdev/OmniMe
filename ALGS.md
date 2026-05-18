# OpalaCoder Algorithms

This document describes the core algorithmic logic and decision flows adopted in OpalaCoder's architecture.

## 1. Double Inference Complexity Algorithm and Dynamic Budgeting

OpalaCoder implements an innovative model known as **Two-Stage Predictive Budgeting** to ensure maximum financial and resolutive efficiency for LLM agents. The goal of this algorithm is to avoid wasting tokens from expensive models on initial planning if the task is trivial, but without compromising the execution if the detailed plan reveals architectural complexities.

The execution is controlled by the `complexity_inference_mode` configuration located in `agents.yaml`, operating in either `simple` or `double` modes.

### Logic Flow (`double` mode)

The algorithm follows these procedural steps:

1. **First Stage: Pre-Plan Heuristic Inference (Strategy 1)**
   - The user submits a prompt with their original request.
   - The `make_complexity_evaluator` receives this raw request and returns one of two complexity labels: `"default"` or `"alternative"`.
   - Based on this label, OpalaCoder chooses the base model that will generate the "Landscape" (Phase 1) and conduct the interactive Refinement (Phase 2).
   - *Purpose:* Ensure that the initial cognitive capacity of the planner is equivalent to the presumed complexity by the user, saving excessive processing on short and simple requests.

2. **Plan Refinement Loop**
   - The plan goes through interactive cycles of human approval. The final outcome of this step is the `approved_plan` text.

3. **Second Stage: Post-Plan JSON Evaluation (Strategy 3)**
   - Instead of jumping straight to execution (as competing agents would do), OpalaCoder intercepts the pipeline before the orchestrator initializes.
   - The `make_post_plan_evaluator` reads the final `approved_plan` line by line.
   - The expected output from this agent is a strict JSON format:
     ```json
     {
       "model": "default | alternative",
       "estimated_steps": <integer>
     }
     ```
   - *Execution Promotion Analysis (`model`)*: The algorithm compares the orchestrator's current model with the JSON prediction. If the JSON concludes that the architecture outlined in the plan is more complex than it seemed in the prompt (requiring `"alternative"`) and the orchestrator was set to `"default"`, the algorithm **upgrades (promotes)** the orchestrator to the alternative model *in-flight*, guaranteeing deep reasoning power for the most critical stage.
   - *Budget Calculation (`max_heartbeats == "auto"`)*: If the orchestration config dictates static heartbeats, nothing changes. However, if it is set to `"auto"`, the ceiling calculation takes effect:
     ```python
     max_hb_config = min(estimated_steps * 3 + 5, 200)
     ```
     The estimated number of steps (e.g., read_file, write_file, run_command) semantically extracted by the LLM is multiplied by a safety margin (3) plus a fixed delta (5), always capped by the maximum logical limit (200), preventing infinite hallucination loops.

4. **Execution**
   - The `AutonomousOrchestratorStrategy` inherits the readjusted `model` and the organically calculated `max_heartbeats`, and triggers the MemGPT instances.

### Fallback Mode (`simple` mode)
If the configuration is set to `simple` or if the JSON Extraction of the *Post-Plan Evaluator* fails due to formatting hallucination:
- In-flight model promotion is ignored.
- If heartbeats are set to `"auto"`, a static contingency ceiling of `max_hb_config = 50` is applied.
