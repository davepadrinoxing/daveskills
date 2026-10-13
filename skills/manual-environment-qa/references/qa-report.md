# QA Report

Use this reference to present a reviewable plan before execution and concise evidence afterward.

## Status Vocabulary

Use exactly one status per scenario:

- `Prepared but not executed`: prerequisites and steps are ready, but no mutation/action was run.
- `Executed and passed`: actual results match all applicable expectations and cleanup is verified.
- `Executed and failed`: execution completed and at least one expected result was wrong.
- `Blocked`: execution or verification could not proceed safely; state the missing prerequisite.
- `Not applicable`: explain why the scenario category or component does not apply.

Do not mark a scenario passed when only part of its required side effects were observed.

## Preparation Summary

Before authorization, report:

```markdown
# QA preparation: <change or behavior>

Environment: <local | Xingbox | preview>
Why this environment: <reason and limitation>
Change/test surfaces: <frontend, HTTP, service, async, integration, platform>

Verified prerequisites:
- <probe, observed result>

Unresolved assumptions or blockers:
- <assumption/blocker or None>

Planned mutations and external effects:
- <exact scope or None>

Cleanup strategy:
- <exact rollback/cleanup and verification>

Scenarios:
- <status> — <scenario and observable oracle>
```

Then request authorization for the exact scenarios and mutations. Do not request deployment authorization implicitly.

## Execution Evidence

Use this structure for each use case:

```markdown
# Use case: <behavior under test>

Status: <Prepared but not executed | Executed and passed | Executed and failed | Blocked | Not applicable>
Environment: <environment and relevant image/commit when available>

$ commands ran

<exact commands or browser actions>

> Received
>
> <actual response/state>
>
> <why the result is correct or incorrect>

Side effects:
- <persisted state, job/queue/message/log/downstream evidence>

Cleanup:
- <command/action and verified result, or reason no cleanup was needed>
```

Use `commands planned` instead of `commands ran` for unexecuted work. Include exact sanitized requests and responses when useful. Never include complete cookies, credentials, tokens, secrets, or unnecessary personal data.

## Final Summary

End with:

- environment and tested image/commit
- count/list by status
- failures and blockers
- cleanup result and any intentionally retained state
- evidence gaps and what the environment could not prove
- optional handoff note for `jira-mob-qa-test-cases` when the user requests Jira publication

## PR Description Draft

When the user supplies a PR link, add a separate paste-ready block matching that repository's `.github/PULL_REQUEST_TEMPLATE.md` QA section. For XTM, use the `## QA (How to test)` heading and checkbox style:

```markdown
## QA (How to test)

- [ ] User path: <where to go, what to do, and the visible expected result>
- [ ] CLI path: `<safe command>` — <expected result>
```

Adapt the number and type of steps to the change; omit a path that does not apply and explain briefly. Keep the draft separate from the evidence report, and do not label unexecuted steps as passed. A PR link alone authorizes preparation of this draft, not editing the live PR description.

Make each PR step specific to the changed surface: backend/Ruby steps should include a runnable `curl` request or Rails method invocation with concrete test inputs and expected output; React steps should give the browser navigation and interaction with the expected visible state; GraphQL steps should include the complete project-appropriate operation, variables, required keys and headers, and expected response. Derive details from the repository/schema and follow the skill's authorization and cleanup rules for writes.
