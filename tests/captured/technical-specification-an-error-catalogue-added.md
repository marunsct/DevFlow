# Technical Specification — Task Management Dashboard

## Reliability and Observability
- Every database mutation (create, update, delete of tasks, users, categories) wrapped in a transaction; the session.commit() call happens in the route function before returning the response. No commit is deferred to teardown.
- Consistent error responses: every error includes HTTP status code, error_code string (e.g., 'DUPLICATE_EMAIL', 'TASK_NOT_FOUND'), and detail message string. Stack traces, SQL queries, internal paths, and database connection details never included in error bodies.
- Health check endpoint GET /api/health returns 200 with {status: 'ok'} when application is running; used by acceptance suite to detect readiness before test execution.
- Pydantic models validate all request bodies at API layer, rejecting invalid input with 422 Unprocessable Entity and field-specific error messages from validation errors.
- Optimistic locking via version column on tasks table: clients must send current version in If-Match header; server returns 409 Conflict with detail 'Version conflict: record has been modified' if mismatch detected.
- FastAPI exception handlers map internal exceptions to appropriate HTTP status codes with consistent JSON error response format.
- Alembic migrations applied at startup for both PostgreSQL and SQLite mode.

## Data Contracts
- UserCreate: {email: 'test@example.com', username: 'testuser', password: 'password123'}. email is string, max 255 chars, RFC 5321 format. username is string, min 3 chars, max 100 chars. password is string, min 8 chars. All fields required.
- UserLogin: {email: 'test@example.com', password: 'password123'}. email is string, max 255 chars. password is string. Both required.
- TokenResponse: {access_token: 'eyJhbGciOiJIUzI1NiIs...', refresh_token: 'a1b2c3d4e5f6...', token_type: 'bearer'}. access_token is JWT string. refresh_token is 64-char hex string. token_type is literal 'bearer'.
- TaskCreate: {title: 'Buy groceries', priority: 'high', description: 'Milk and bread', due_date: '2025-12-31T23:59:59Z', category_id: '550e8400-e29b-41d4-a716-446655440000', tags: ['personal', 'shopping'], reminders: ['2025-12-30T10:00:00Z']}. title is string 1-255 chars. priority is one of low/medium/high/urgent. description is optional string max 10000 chars. due_date is optional ISO 8601 datetime string not in past. category_id is optional UUID. tags is optional array of strings. reminders is optional array of ISO 8601 datetime strings.
- TaskUpdate: {title: 'Updated title', status: 'in_progress'}. All fields optional. Same constraints as TaskCreate fields where provided.
- TaskResponse: {id: '550e8400-e29b-41d4-a716-446655440000', title: 'Buy groceries', description: 'Milk and bread', priority: 'high', due_date: '2025-12-31T23:59:59Z', status: 'todo', category_id: '550e8400-e29b-41d4-a716-446655440000', assignee_id: null, creator_id: '550e8400-e29b-41d4-a716-446655440001', version: 0, tags: ['personal', 'shopping'], reminders: ['2025-12-30T10:00:00Z'], created_at: '2025-01-01T12:00:00Z', updated_at: '2025-01-01T12:00:00Z'}. id is UUID string. title is string. description is string or null. priority is one of low/medium/high/urgent. due_date is ISO 8601 string or null. status is one of todo/in_progress/done. category_id is UUID string or null. assignee_id is UUID string or null. creator_id is UUID string. version is integer. tags is array of strings. reminders is array of ISO 8601 datetime strings. created_at/updated_at are ISO 8601 datetime strings.
- CategoryCreate: {name: 'Work'}. name is string, min 1 char, max 100 chars. Required.
- CategoryResponse: {id: '550e8400-e29b-41d4-a716-446655440000', name: 'Work', user_id: '550e8400-e29b-41d4-a716-446655440001', created_at: '2025-01-01T12:00:00Z'}. id is UUID string. name is string. user_id is UUID string. created_at is ISO 8601 datetime string.
- AnalyticsResponse: {total_tasks: 7, tasks_by_priority: {low: 2, medium: 3, high: 1, urgent: 1}, tasks_by_status: {todo: 5, in_progress: 3, done: 2}, overdue_count: 1}. total_tasks is integer. tasks_by_priority maps priority string to integer count. tasks_by_status maps status string to integer count. overdue_count is integer.
- PaginatedResponse: {items: [TaskResponse], total: 25, page: 1, page_size: 10}. items is array of TaskResponse objects. total is integer count of all matching records. page is integer current page number. page_size is integer number of items per page.
- Error: {detail: 'Email already registered', error_code: 'DUPLICATE_EMAIL'}. detail is a human-readable string. error_code is a machine-readable string identifying the error type.

## Error Catalogue
- DUPLICATE_EMAIL (409 Conflict): Returned when POST /api/v1/auth/register is called with an email address that already exists in the database. The request body is unchanged.
- VALIDATION_ERROR (422 Unprocessable Entity): Returned when any POST or PUT request body fails Pydantic validation — missing required fields, invalid email format (not RFC 5321), password shorter than 8 characters, username outside 3–100 character range, priority not in ['low', 'medium', 'high', 'urgent'], status not in ['todo', 'in_progress', 'done'], due_date is a valid ISO 8601 datetime but in the past, or other field constraint violations. The request body is unchanged.
- INVALID_CREDENTIALS (401 Unauthorized): Returned when POST /api/v1/auth/login is called with an email that exists but the password does not match bcrypt's check, or when no user record is found for the given email. The request body is unchanged.
- TOKEN_NOT_FOUND (404 Not Found): Returned when POST /api/v1/auth/refresh is called with a refresh_token value whose SHA-256 hash does not match any row in the refresh_tokens table, or the matching row has expires_at <= now, or the matching row has revoked = true. The request body is unchanged.
- TASK_NOT_FOUND (404 Not Found): Returned when GET, PUT, or DELETE /api/v1/tasks/{task_id} is called with a UUID that does not match any task record in the database. The resource is unchanged.
- CATEGORY_NOT_FOUND (404 Not Found): Returned when GET, PUT, or DELETE /api/v1/categories/{category_id} is called with a UUID that does not match any category record. The resource is unchanged.
- FORBIDDEN_ACCESS (403 Forbidden): Returned when an authenticated user attempts to read, update, or delete a task where neither creator_id nor assignee_id matches the current user's id, or when attempting to delete a category whose user_id does not match the current user. The resource is unchanged.
- VERSION_CONFLICT (409 Conflict): Returned when PUT /api/v1/tasks/{task_id} is called with an If-Match header containing an integer that does not equal the task's current version column value. The task record is unchanged.
- DUPLICATE_CATEGORY (409 Conflict): Returned when POST /api/v1/categories is called with a name that already exists for the same user_id, violating the UNIQUE(name, user_id) constraint. The request body is unchanged.
- RATE_LIMITED (429 Too Many Requests): Returned when POST /api/v1/auth/register receives more than 5 requests per minute from the same client IP address, or when POST /api/v1/auth/login or POST /api/v1/auth/logout receives more than 10 requests per minute from the same client IP address. The request body is unchanged.
- UNAUTHORIZED (401 Unauthorized): Returned on any endpoint that requires authentication when the Authorization header is missing, does not start with 'Bearer ', or contains a JWT token that fails algorithm check, has expired, or has a jti present in the revoked_tokens table. The resource is unchanged.

## Specialist Advice and Decisions
- UX-1: adopted - interface_design
- UX-2: adopted - interface_design
- UX-3: adopted - interface_design
- UX-4: adopted - interface_design
- UX-5: adopted - interface_design
- UX-6: adopted - interface_design
- UX-7: adopted - interface_design
- UX-8: adopted - interface_design
- UX-9: adopted - interface_design
- DB-1: adopted - domain_model
- DB-2: adopted - domain_model
- DB-3: adopted - domain_model
- DB-4: adopted - domain_model
- DB-5: adopted - domain_model
- BE-1: adopted - data_flows
- BE-2: adopted - security_and_privacy
- BE-3: adopted - domain_model
- BE-4: adopted - api_and_event_contracts
- BE-5: adopted - error_catalogue
- BE-6: adopted - reliability_and_observability
- BE-7: adopted - api_and_event_contracts
- BE-8: adopted - api_and_event_contracts
- BE-9: adopted - api_and_event_contracts
- BE-10: adopted - configuration
- SR-1: adopted - security_and_privacy
- SR-2: adopted - security_and_privacy
- SR-3: adopted - api_and_event_contracts
- SR-4: adopted - data_flows
- SR-5: adopted - security_and_privacy
- SR-6: adopted - reliability_and_observability
- SR-7: adopted - error_catalogue
- SR-8: adopted - security_and_privacy
- SR-9: adopted - security_and_privacy
- SR-10: adopted - security_and_privacy
- TS-1: adopted - test_cases
- TS-2: adopted - test_cases
- TS-3: adopted - test_cases
- TS-4: adopted - test_cases
- TS-5: adopted - test_cases
- TS-6: adopted - test_cases
- TS-7: adopted - test_cases
- TS-8: adopted - test_cases
- TS-9: adopted - test_cases
- TS-10: adopted - test_cases
