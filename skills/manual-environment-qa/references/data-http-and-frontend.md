# Data, HTTP, and Frontend QA

Use this reference for schema-aware preparation, independently verified API behavior, and browser-observable React/frontend checks.

## Discover Data Before Setup

Start from current code and the target database. Do not infer columns or relationships from names.

1. Inspect the model, schema, scopes, validations, callbacks, and nearby factories/specs.
2. Print `column_names` and association metadata from the target runtime.
3. Resolve user permissions through actual associations. In XTM, users connect to companies through seats; do not assume a direct user company column.
4. Query candidate, pool candidate, project, pool, status, and other workflow records with `unscoped` when default scopes could hide archived, removed, or soft-deleted rows.
5. Before creation scenarios, explicitly prove that the target `Candidate` or `PoolCandidate` does not already exist with `Candidate.unscoped` or `PoolCandidate.unscoped` and the verified natural keys.
6. Capture baseline counts and state for the exact record IDs.
7. Choose identities already known to required dependency systems. Never invent identity, client, company, project, pool, or candidate IDs.

Example read-only Rails probe:

```ruby
user = User.unscoped.find_by(identity_id: <verified_identity_id>)
seats = user&.seats&.includes(:company)&.map do |seat|
  { seat_id: seat.id, seat_type: seat.seat_type, company_id: seat.company_id, client_id: seat.company.client_id }
end
pp({ user_id: user&.id, identity_id: user&.identity_id, seats: seats })
```

Keep output limited to the fields needed for QA.

## Use MySQL Narrowly

Prefer ActiveRecord for setup because it respects the current schema, validations, callbacks, and associations. Use MySQL for:

- read-only reconnaissance
- `SHOW COLUMNS FROM <verified_table>` when model assumptions fail
- independent verification after an HTTP/UI action
- narrowly scoped setup only when ActiveRecord is unsuitable and the user explicitly authorizes it

The usual local/Xingbox database is `cra_development`, but always verify `ActiveRecord::Base.connection.current_database` or `SELECT DATABASE()` first.

Before any SQL write:

- show the exact statement
- prove every target with a read-only `SELECT`
- capture the old values
- define an exact inverse operation using verified IDs or a unique QA marker
- confirm the target is not production

Never use an unbounded `UPDATE` or `DELETE`.

## Choose a Containment Strategy

### In-process synchronous QA

Use a rollback transaction when setup, request, verification, and cleanup all run synchronously in one Rails process:

```ruby
created_id = nil

ActiveRecord::Base.transaction(requires_new: true) do
  record = <Model>.create!(<verified_attributes>)
  created_id = record.id

  # Run the authorized in-process behavior and assertions here.

  raise ActiveRecord::Rollback
end

puts({ rolled_back: !<Model>.unscoped.exists?(created_id) })
```

Do not use this containment claim for a separate browser/server process. A rollback transaction also suppresses or changes `after_commit` behavior and cannot reverse jobs, AMQP/Kafka publication, external calls, or separately committed connections.

### Committed or asynchronous QA

When a real server, browser, `after_commit`, worker, consumer, or external system is involved:

- create the smallest record set
- tag records with a unique, searchable QA marker when the model safely permits it
- record every created ID and every changed old value
- define cleanup before mutation
- verify downstream cleanup requirements separately

Do not reuse `CypressController#cleanup`: it truncates tables and is unsafe for manual environment QA.

## Verify HTTP and API Behavior

For each GraphQL or REST request, capture:

- method and recognized route
- authenticated identity/client context
- request path, sanitized headers, and body/variables
- response status, media type, and relevant sanitized body fields
- expected versus actual persistence
- expected versus actual job/message/external effects
- negative behavior for invalid input or missing permission

For GraphQL, inspect the current `*.gql`, `schema.graphql`, generated types, resolver, and authorization path. Do not hand-edit generated artifacts. Hand GraphQL contract uncertainty to `graphql-contract-guardian`.

Verify persisted state independently with a fresh ActiveRecord query or a narrow MySQL `SELECT`. Avoid using only the response object as proof of persistence.

## Prepare Frontend QA

For React or legacy-boundary behavior, define:

- exact URL and navigation path
- authenticated account, seat/company, role, permissions, locale, feature flags, and experiments
- required backend record IDs and states
- loading, empty, error, and success states
- expected REST/GraphQL requests and relevant response shapes
- visible result and persistence after refresh, back/forward navigation, or revisiting the route
- boundary values and permission/flag-off behavior
- regression-sensitive neighboring flows
- responsive and accessibility checks when the UI surface makes them relevant
- browser console, network, and tracking inspection when relevant

Prefer browser-observable results. Use Rails/MySQL only to establish or independently verify the required state.

For accessibility, check keyboard reachability, focus order/return, semantic role/name, disabled/expanded/selected state, and error announcements where relevant. For responsive behavior, identify explicit viewports rather than saying only “check mobile.”

If automation or a changed Cypress flow is requested, hand it to `cypress-maintenance`; do not silently create a Cypress spec.

## Scenario Matrix

Use only applicable categories:

- Positive: authorized user and valid state produce the expected result.
- Negative: invalid input, missing permission, or invalid transition is rejected without unintended state.
- Boundary: empty/one/many records, min/max input, archived/removed state, duplicate request, or retry boundary.
- Regression: coupled navigation, shared component, existing API consumer, or prior state still works.

For every scenario, include an observable oracle. “No error” alone is insufficient when persistence or side effects matter.
