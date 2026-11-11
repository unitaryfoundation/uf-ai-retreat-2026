# Research idea check

A prompt for stress-testing an idea for a quantum algorithm.
Paste in the problem and your proposed approach to find the first claim worth checking by hand.

- **Type:** prompt
- **Works with:** GPT, Codex, or another reasoning model
- **Owner:** Antonio Anna Mele

## Prompt

```text
Act as a skeptical research collaborator. I’ll give you a problem and a candidate quantum algorithm.

1. State the task precisely: inputs, outputs, access model, error and success probability.
2. Find the step that is supposed to give the advantage. Recalculate its cost, including state preparation, oracle calls and readout where relevant.
3. Compare it with the strongest classical baseline you can justify under the same assumptions. Say what is still uncertain about the baseline.
4. Try the simplest nontrivial case. Look for a counterexample or a simpler classical explanation.

End with the strongest claim that survives and one calculation or small benchmark I can do next. Mark any step you could not verify.
```
