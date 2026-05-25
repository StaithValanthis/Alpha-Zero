# Strategy Diversity Monitor
# Model: groq/llama-3.3-70b-versatile | tier: ops_standard

## Introduction
The Strategy Diversity Monitor is a weekly analyst that audits strategy archetype coverage by reading state/strategies.json and state/lessons.json. The agent outputs a structured gap report to data/analyst_reports/strategy_diversity.json, listing which archetypes are covered and which are absent. This report is consumed by the chief-evaluator and orchestrator during Sunday review.

## Inputs
- state/strategies.json
- state/lessons.json
- state/research.json (for dominant regime context)

## Outputs
- data/analyst_reports/strategy_diversity.json

## Pipeline Position
The Strategy Diversity Monitor is a standalone agent.

## Operation
The agent will be triggered every Sunday at 20:00, as part of the weekly review process. It will read the input files, analyze the strategy archetype coverage, and output a gap report to data/analyst_reports/strategy_diversity.json.

## Output JSON Schema
The output JSON file, data/analyst_reports/strategy_diversity.json, will have the following schema:
```json
{
  "archetypes": [
    {
      "name": "string",
      "covered": "boolean"
    }
  ],
  "gaps": [
    {
      "name": "string",
      "reason": "string"
    }
  ],
  "summary": {
    "total_archetypes": "integer",
    "covered_archetypes": "integer",
    "uncovered_archetypes": "integer"
  }
}
```
## Interpretation Guidelines
The gap report will provide the following key metrics:

* `archetypes`: A list of all strategy archetypes, with a boolean indicating whether each archetype is covered.
* `gaps`: A list of archetypes that are not covered, with a reason for the gap.
* `summary`: A summary of the total number of archetypes, the number of covered archetypes, and the number of uncovered archetypes.

The chief-evaluator and orchestrator will use this report to identify areas where strategy archetype coverage is lacking and take corrective action to address these gaps.

## Example Output
```json
{
  "archetypes": [
    {
      "name": "Trend Following",
      "covered": true
    },
    {
      "name": "Mean Reversion",
      "covered": false
    },
    {
      "name": "Statistical Arbitrage",
      "covered": true
    }
  ],
  "gaps": [
    {
      "name": "Mean Reversion",
      "reason": "No strategies found for this archetype"
    }
  ],
  "summary": {
    "total_archetypes": 3,
    "covered_archetypes": 2,
    "uncovered_archetypes": 1
  }
}
```