# Submission readiness — checked 19 October 2026

Source of requirements: [official Microsoft rules](https://github.com/microsoft/insidethegamehackathon/blob/main/OFFICIAL%20RULES.md), sections 1, 4 and 6.

Registration closes **20 October, 12:00 Pacific / 22:00 Israel**. Submission
closes **27 October, 23:59 Pacific / 28 October, 08:59 Israel**. Confirm that the
team is registered; repository work does not register or submit a project.

| Requirement / focus | Current evidence | Remaining action |
| --- | --- | --- |
| Synthetic football events | Existing synthetic generator and SSE engine | Use synthetic playback in the final demo; distinguish historical research |
| Ingest, interpret, explain, render, personalize | Metrics, recommendations, replay, new explanation API; English/Hebrew and three audiences | Connect explanations to the final demo and verify the complete flow |
| Microsoft technology use | Azure OpenAI v1 adapter implemented | Create resource/deployment and demonstrate successful live calls; configuration alone is insufficient |
| Public GitHub repository | Team repository is public and merged to main at the checked base | Merge reviewed integration and provide installation/testing instructions |
| Demo video under two minutes | Not verified | Show working synthetic flow and real Microsoft integration |
| English submission or English translations | English technical documentation and explanation mode available | English pitch, testing instructions and video/translation |
| Working access for judging through judging period | Local demo works; no hosted deployment verified | Supply accessible site or test build; keep available through 10 November |
| Original work and authorized assets | Research sources and synthetic assumptions documented | Review final included assets, data and branding permissions |

Microsoft's five equally weighted criteria are technical implementation,
agentic design/innovation, impact, user experience/presentation and category
fit. Foundry and Azure cloud integration have category prizes; this does not
mean every listed Microsoft product must be added. Our bounded narrative
planner is not a multi-agent system. Do not describe unimplemented services as
part of the deployed stack.

## Practical finish order

1. Team confirms registration immediately; Azure account owner configures the
   resource, deployment and credentials locally. No subscription was created here.
2. Merge the isolated explanation module into the teammate's current main;
   connect its response beside the unchanged engine result.
3. Complete the real Azure smoke test, then assess explanation selection,
   responsiveness and fallback behavior on representative synthetic states.
4. Finish coach controls and deterministic calibration; explanations must
   reflect the new state rather than infer a missing objective.
5. Prepare the final synthetic demo, testing access, English pitch and video.

Status is a repository-based review, not organizer acceptance. Historical match
replay remains useful for analysis and should not be presented as the final
synthetic live feed. There is no claim that a language model fixes the current
freshness/tactical imbalance.
