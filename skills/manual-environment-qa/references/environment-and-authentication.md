# Environment and Authentication

Use this reference to select an XTM QA environment, prove prerequisites incrementally, and establish an authenticated Rails or browser session safely.

## Environment Decision

### Local Docker

Choose local Docker when the behavior can be proven with the checked-out code and local services. It is the default for isolated database changes, Rails requests, React behavior, and controlled Sidekiq/AMQP checks.

Start with read-only probes:

```sh
make status
docker compose exec app bundle exec rails runner 'puts Rails.env'
docker compose exec app bundle exec rails runner 'puts ActiveRecord::Base.connection.current_database'
```

Expected results:

- required containers are running
- Rails reports `development` unless the local invocation intentionally overrides it
- the database name is observed rather than assumed; the usual local default is `cra_development`

Use `.agent/docs/developing-with-docker.md` for startup and logs. Do not run `make db-reset`, `make uninstall`, or cleanup commands as routine QA.

The `/xtm/_cypress/login` route is not mounted in the normal local `development` environment. Use the supported local login flow or an already established session whose identity/client context can be verified. Do not invent an authentication bypass; stop if safe local authentication is unavailable.

### Xingbox

Choose Xingbox when XTM must use Xingbox-hosted dependencies or the sandbox authentication flow. Verify the environment from the target runtime; Xingbox normally reports `development_sandbox`, but do not assume it.

Use the team-supported shell/exec mechanism for the target Xingbox, then run small Rails probes such as:

```sh
bundle exec rails runner 'puts Rails.env'
bundle exec rails runner 'puts ActiveRecord::Base.connection.current_database'
```

Do not invent a Xingbox CLI command when none is documented in the repository. Ask the user to run the Rails probe in the known target shell if access is unavailable.

### Shared preview

Choose preview only when deployed Odyssey configuration, image behavior, or shared dependencies must be observed. Before deployment or disruptive testing:

- obtain the preview lock and coordinate in the team thread documented in `.agent/docs/deploying-to-preview.md`
- verify the target PR/SHA or image tag
- verify the successful deployment workflow and actual pod image
- treat preview as shared and non-production-equivalent

The Xingbox Cypress fake-login endpoint is not mounted in preview. Use the supported preview authentication/session mechanism. Stop if it cannot be established safely.

Read-only preview reconnaissance does not itself require taking the deployment lock under this skill. The documented preview lock/team coordination is mandatory before deployment or disruptive testing; continue to follow any stricter current team access rule.

## Incremental Rails Probes

Run only the probes relevant to the change. Replace placeholders only after inspecting the route/model from current code.

Verify environment and database:

```ruby
puts Rails.env
puts ActiveRecord::Base.connection.current_database
```

Verify a route before requesting it:

```ruby
pp Rails.application.routes.recognize_path("/xtm/<path>", method: :get)
```

Use the actual HTTP verb. A recognition error is a prerequisite failure, not permission to guess another endpoint.

Verify model shape and relationships:

```ruby
pp <Model>.column_names.sort
pp <Model>.reflect_on_all_associations.map { |a| [a.macro, a.name, a.class_name] }
```

Verify exact records without mutating them:

```ruby
record = <Model>.unscoped.find_by(id: <verified_id>)
pp({ found: !record.nil?, id: record&.id })
```

Prefer counts, stable IDs, and state names over unnecessary personal data in evidence.

## Xingbox Fake Login

XTM mounts `POST /xtm/_cypress/login` only when `Rails.env.test?` or `Rails.env.development_sandbox?`. The route is defined conditionally in `config/routes.rb`, and `CypressController` enforces the same restriction. Never use or expect it in preview or production.

Before login:

1. Verify `Rails.env` is `development_sandbox` (or `test`).
2. Verify the route with `Rails.application.routes.recognize_path`.
3. Verify the identity ID and client ID exist in XTM/dependency systems and have the required relationship.
4. Capture the existing user, seat/company, locale, and onboarding-setting baseline and define cleanup if the login could change them.
5. Obtain mutation authorization: fake login calls `User.find_or_create_new` and updates locale/onboarding settings, so it is not a read-only probe.
6. Use the same integration-session object for fake login and all subsequent requests.

A Rails-native session pattern is:

```ruby
session = ActionDispatch::Integration::Session.new(Rails.application)
session.host! "<verified-host>"
session.https!

puts({ cookies_before: session.cookies.to_hash.keys.sort })

session.post(
  "/xtm/_cypress/login",
  params: {
    fake_user_id: <verified_identity_id>,
    fake_client_id: <verified_client_id>,
    locale: "en"
  }
)

puts({ login_status: session.response.status, cookie_names: session.cookies.to_hash.keys.sort })
```

A new integration session has no cookies. A successful fake-login response is normally `204`; verify the response rather than assuming it. Print cookie names only, never values.

Then make an authenticated GET with the same object to verify authorization and initialize CSRF state when required:

```ruby
session.get("/xtm/<verified-safe-get>")
puts({ get_status: session.response.status, location: session.response.headers["Location"], cookie_names: session.cookies.to_hash.keys.sort })
```

Do not proceed to mutations until login and the GET behave as expected.

## XTM CSRF Flow

XTM uses the `xing-csrf_protection` gem. Frontend code reads the token from the `xing_csrf_token` cookie; do not assume a `<meta name="csrf-token">` element is present.

- keep `xing_csrf_checksum` in the integration/browser cookie jar; it is HTTP-only
- read `xing_csrf_token` only inside the session that will make the request
- send that token in `X-CSRF-Token`
- never print or copy either complete cookie value into evidence

After the authenticated GET, verify cookie presence without values:

```ruby
cookie_names = session.cookies.to_hash.keys.sort
puts({ csrf_token_present: cookie_names.include?("xing_csrf_token"), csrf_checksum_present: cookie_names.include?("xing_csrf_checksum") })
```

For an authorized mutating request:

```ruby
csrf_token = session.cookies["xing_csrf_token"]
raise "missing CSRF token" if csrf_token.to_s.empty?

session.post(
  "/xtm/<verified-path>",
  params: <verified_params>,
  headers: { "X-CSRF-Token" => csrf_token }
)

puts({ status: session.response.status, content_type: session.response.media_type })
```

Keep the same `session`; constructing another integration session loses the authenticated cookie jar. Verify authentication, CSRF cookie presence, route recognition, and authorization independently so a failure has one clear cause.

## Browser Authentication

- Local/Xingbox Cypress helpers use `POST /xtm/_cypress/login`, but this skill does not create or modify Cypress specs.
- For manual browser work, use the environment-supported login and inspect cookie names/presence through browser tooling without recording values.
- For preview, use its supported login flow; never copy a local/Xingbox session into preview.
- Record the tested role, client/company context, locale, feature flags, and permissions without exposing credentials.
