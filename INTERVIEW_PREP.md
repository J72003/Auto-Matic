# DealerLot — Interview Prep (Cox Automotive, entry-level SWE)

Use this to defend the project and cover the fundamentals the job description calls out.
The golden rule: **never claim something you can't explain.** A simpler honest answer beats
a buzzword you can't unpack.

---

## 0. Your 60–90 second project pitch (memorize the shape, not the words)

> "DealerLot is a full-stack web app for a car dealership. It does two things Cox does in
> real life — manage lot inventory like vAuto, and value cars like Kelley Blue Book.
> It's a Flask REST API backed by SQLite, with a JavaScript frontend, and a machine-learning
> model that estimates a car's market price. I trained a RandomForest in scikit-learn, exported
> it to JSON, and run inference in pure Python so the deployed app stays lightweight. I deployed
> it to Render with a health-check endpoint and wrote a pytest suite for the API."

Then stop and let them pick a thread. Don't monologue.

---

## 1. Project deep-dive questions (most likely)

**Q: Walk me through the architecture.**
Frontend (HTML/JS) → REST API (Flask) → repository layer → SQLite. A separate ValuationService
loads the ML model. The key idea is separation of concerns: `app.py` only does HTTP wiring,
`core/models.py` is the domain object, `core/repository.py` is the only place that touches SQL,
`core/valuation.py` is the only place that knows about the model.

**Q: Why the repository pattern?**
So SQL lives in exactly one class. The route handlers depend on `VehicleRepository`'s methods
(`list`, `add`, `delete`), not on sqlite directly. If we later moved to Postgres, I'd rewrite
one class and nothing else changes. It also makes the API easy to test because I can reason
about data access in isolation.

**Q: What is `create_app()` and why a factory?**
It's the application-factory pattern — a function that builds and returns the Flask app instead
of creating it at import time. It lets me spin up a fresh app with different config (e.g. a
throwaway test database) per test, which is exactly what my `conftest.py` does.

**Q: How does the valuation model actually produce a number?**
It's a RandomForest — an ensemble of 40 decision trees. Each tree walks the input
(base price, age, mileage, condition, accidents) down to a leaf and returns a value; I average
the 40 results. I trained it on the *log* of price (prices are right-skewed), so I exponentiate
the average to get dollars. The spread across the trees gives me a rough confidence band.

**Q: Why export to JSON instead of pickling the sklearn model?**
So the deployed service doesn't need scikit-learn or numpy at runtime — just Flask. Smaller image,
faster cold start, fewer dependency/security headaches. The JSON is just each tree's arrays
(feature, threshold, children, leaf values) and I traverse them with a short loop.

**Q: How do you prevent SQL injection?**
Every query uses parameterized statements (`?` placeholders), never string formatting. The user's
input is passed as data, never concatenated into the SQL text.

**Q: How is input validated?**
The `Vehicle.from_payload()` factory coerces types and `validate()` enforces business rules
(year range, mileage range, condition 1–5, positive price). Bad input returns HTTP 400 with a
message; it never reaches the database.

**Q: What would you change / what are the weaknesses?**
Be honest and specific. Good answers:
- The model is trained on synthetic data — I'd swap in a real dataset (the code already takes `--csv`).
- SQLite is single-writer; for real concurrency I'd move to Postgres.
- No auth — I'd add login/roles before real dealers used it.
- The frontend re-fetches a valuation per row on every load; I'd cache or batch that.
- I'd add CI (run pytest on every push) and structured logging/metrics for real monitoring.

**Q: How would you scale this to thousands of dealers?**
Postgres with connection pooling, the valuation behind its own service, caching for repeat
estimates, pagination on the inventory list, and a load balancer in front of multiple app
instances. Keep the app stateless so you can run many copies.

**Q: How did you test it?**
A pytest suite hitting the Flask test client: health check, CRUD round-trip, validation rejects
bad data, valuation is in a sane range, unknown make falls back gracefully. Each test gets an
isolated temp database.

---

## 2. OOP fundamentals (required bullet — they will ask)

- **Encapsulation:** bundling data + behavior and hiding internals. `VehicleRepository` hides the
  SQL; callers just call methods. (Underscore-prefixed `_conn` signals "private.")
- **Abstraction:** exposing *what* not *how* — the API depends on `repo.list()`, not on SQL.
- **Inheritance:** a subclass reusing/extending a parent. My `ValidationError` extends `ValueError`.
- **Polymorphism:** same interface, different behavior — e.g. `from_row()` vs `from_payload()` both
  produce a `Vehicle` from different sources.
- **Class vs object/instance:** `Vehicle` is the class (blueprint); a specific Camry row is an instance.
- **`@dataclass`:** auto-generates `__init__`, etc., for classes that mainly hold data.
- Know **composition vs inheritance** and "prefer composition" — my app composes services rather
  than building deep inheritance trees.

---

## 3. Database / SQL (required bullet)

Be ready to **write a query on a whiteboard.** Practice these against the `vehicles` table:
- Select all available BMWs: `SELECT * FROM vehicles WHERE status='available' AND make='BMW';`
- Count by status: `SELECT status, COUNT(*) FROM vehicles GROUP BY status;`
- Average asking price per make: `SELECT make, AVG(asking_price) FROM vehicles GROUP BY make;`
- Most expensive 3: `... ORDER BY asking_price DESC LIMIT 3;`

Concepts to be able to explain:
- **Primary key** (unique row id), **foreign key** (link between tables).
- **Index** — speeds up reads on a column at the cost of slower writes; I indexed `status`
  because the app filters on it. Know that it's like a book's index.
- **JOIN** — combine rows from two tables (INNER vs LEFT). My schema is one table, so be ready to
  describe how you'd add a `dealers` table and join on `dealer_id`.
- **Normalization** — splitting data to avoid duplication (e.g. don't repeat dealer address on
  every vehicle row).
- **Transaction / ACID** — a group of statements that all succeed or all roll back.
- **SQL vs NoSQL** — relational/structured vs flexible/document; know one tradeoff each.

---

## 4. Web / REST (the "plus" bullet)

- **REST** = resources (URLs) + HTTP verbs. GET read, POST create, PUT update, DELETE remove.
- **Status codes:** 200 OK, 201 Created, 204 No Content, 400 Bad Request, 404 Not Found, 500 Server Error.
  Point to where you return each in `app.py`.
- **Client–server:** browser sends an HTTP request, server returns JSON, JS renders it.
- **Idempotency:** GET/PUT/DELETE can be repeated safely; POST creates each time.
- **Stateless:** each request carries what it needs; the server doesn't remember the last one.
- Bonus: what's an API, what's JSON, what is CORS (briefly).

---

## 5. Coding exercise — what to drill

Expect one easy/medium problem. Highest-yield topics for entry-level:
- Arrays & strings: two pointers, reverse, dedupe.
- **Hash maps / sets** (the single most common tool): "two sum," counting frequencies, detect duplicates.
- Basic sorting + searching; binary search.
- Big-O: be able to say a hash-map lookup is O(1) and a nested loop is O(n²).
Practice ~15–20 LeetCode *Easy* problems out loud, narrating your thinking. They care about
communication and approach as much as the final code. **Think out loud, state assumptions,
test your answer on a small example.**

---

## 6. Behavioral (Cox weights this heavily — use STAR)

STAR = Situation, Task, Action, Result. Prepare 4–5 stories you can flex to many questions.
The JD signals these themes — have a story for each:
- **Collaboration / teamwork:** a group project; how you divided work, handled a teammate conflict.
- **Communication:** explaining something technical to a non-technical person.
- **Initiative / self-motivation / ambition:** *DealerLot is a perfect story here* — you taught
  yourself the stack and shipped a deployed app on your own.
- **Handling failure / debugging under pressure:** a bug you chased down; what you learned.
- **Fast-paced / ambiguity:** a deadline or shifting requirements you adapted to.

Classic prompts: "Tell me about yourself," "Why Cox Automotive?", "Tell me about a project
you're proud of" (→ DealerLot), "A time you disagreed with a teammate," "A time you failed,"
"How do you handle feedback / a code review?"

**Why Cox** — have a real answer: their scale (Manheim, KBB, Autotrader), the end-to-end
automotive ecosystem, and that you built a project around their actual products. Tie it to wanting
to learn on a collaborative team that does code reviews and mentoring (straight from their JD).

---

## 7. Smart questions to ask them (always have 3–4)

- "What does a typical sprint look like for your team?"
- "How is code review and mentoring handled for new engineers here?"
- "What does the first 90 days look like for someone in this role?"
- "What's the tech stack the team uses day to day?"
- "What separates someone who does well in this role from someone who struggles?"

---

## 8. Logistics / don't-trip-yourself-up

- Run the app and click through it the morning of, so a demo never fails live.
- Have the GitHub repo and live URL ready in a tab.
- If asked something you don't know: say so, then reason about it out loud. "I haven't used X,
  but based on Y I'd expect…" Coachability beats bluffing.
- Be ready to share screen and walk the code top-down: `app.py` → `core/` → `static/index.html`.
- Frame honestly: it's a personal learning project, not production software used by real dealers.
