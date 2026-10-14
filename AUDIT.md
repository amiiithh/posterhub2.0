# PosterHub — completeness audit

Scope: the entire project in this working tree (2,798 lines across `shop/`, `posterhub/`, templates).
Every finding was reproduced with a command; none is inferred from reading alone. Re-run instructions are in
"How this was verified" and in each finding.

## Severity summary

| Severity | Count | Meaning here |
| --- | --- | --- |
| **Critical** | 1 | Prevents the application from starting at all |
| **High** | 4 | Broken page (HTTP 500) or silently wrong/blank data in a user-facing feature |
| **Medium** | 9 | Dead or unreachable code, half-finished feature with a visible effect, deploy blocker |
| **Low** | 10 | Cosmetic, docs, housekeeping |
| **Total** | **24** | |

## Findings register

| ID | Severity | Location | Issue |
| --- | --- | --- | --- |
| F1 | Critical | [views_admin.py:5](shop/views_admin.py#L5) + untracked `shop/forms.py` | Committed code imports a module that was never committed; a fresh clone cannot start |
| F2 | High | [admin_order_detail.html:20](shop/templates/admin_order_detail.html#L20), [:40](shop/templates/admin_order_detail.html#L40), [:109](shop/templates/admin_order_detail.html#L109), [:123](shop/templates/admin_order_detail.html#L123) | Four invalid template constructs — `/manage/orders/<pk>/` returns HTTP 500 |
| F3 | High | [admin_order_detail.html:105-112](shop/templates/admin_order_detail.html#L105-L112) + [views_admin.py:67-78](shop/views_admin.py#L67-L78) | Item-quantity editing is unreachable: no submit button, "Edit Qty" is `href="#"` |
| F4 | High | [admin_orders.html:20](shop/templates/admin_orders.html#L20), [:28](shop/templates/admin_orders.html#L28), [:32](shop/templates/admin_orders.html#L32) | Total-sales / Processing / Shipped cards render blank — the view never passes those values |
| F5 | High | [admin_dashboard.html:45](shop/templates/admin_dashboard.html#L45) | "Orders by status" card renders empty — loops over `statuses`, which no view provides |
| F6 | Medium | [admin_dashboard.html:50](shop/templates/admin_dashboard.html#L50), [:53](shop/templates/admin_dashboard.html#L53) | `status_counts.val` is a literal dict key named `val`, so every bar would be 0% |
| F7 | Medium | [forms.py:22](shop/forms.py#L22), [:30](shop/forms.py#L30), [views.py:100](shop/views.py#L100) | `OrderAdminForm` is never imported, so its phone validation never runs; checkout stores the raw value |
| F8 | Medium | [models.py:58](shop/models.py#L58), [profile.html:96](shop/templates/profile.html#L96), `checkout.html` | Coupons are display-only: no coupon field at checkout, no discount column on `Order` |
| F9 | Medium | [login.html](shop/templates/registration/login.html) + missing `registration/password_reset_*.html` | Password reset is served by Django's *admin* templates and is unreachable (no link on the login page) |
| F10 | Medium | [base.html:177](shop/templates/base.html#L177) | Staff nav link still points at Django's `/admin/`; the new `manage/` pages are linked from nowhere |
| F11 | Medium | [views_admin.py](shop/views_admin.py) `admin_posters` | Passes `categories` (a full poster queryset) that the template never uses — one wasted query per load |
| F12 | Medium | [settings.py:32](posterhub/settings.py#L32) | No `STATIC_ROOT`; `collectstatic` fails with exit 1, so the project cannot be deployed |
| F13 | Medium | [views_admin.py:67-78](shop/views_admin.py#L67-L78) | Bare `pass` swallows a `ValueError` while parsing item quantity; the request silently succeeds |
| F14 | Low | [admin_order_detail.html:111](shop/templates/admin_order_detail.html#L111) | "Edit Qty →" is a dead `href="#"` link |
| F15 | Low | [forms.py:2-3](shop/forms.py#L2-L3) | Three unused imports (`Q`, `Category`, `OrderItem`) |
| F16 | Low | [\_grid.html](shop/templates/_grid.html) + [\_art.html](shop/templates/_art.html) | Dead templates — nothing includes `_grid.html`; `_art.html` is included only by it |
| F17 | Low | [views_admin.py:93](shop/views_admin.py#L93), [:101](shop/views_admin.py#L101) | `total` is computed twice (the second line silently overwrites the first) |
| F18 | Low | [models.py:24](shop/models.py#L24), [:41](shop/models.py#L41), [:73](shop/models.py#L73) | `Wishlist`, `OrderItem` and `Review` have no `__str__`, so admin shows "OrderItem object (1)" |
| F19 | Low | [admin_posters.html:30-35](shop/templates/admin_posters.html#L30-L35) | `{{ form.field }}` renders raw unstyled widgets; the `widgets` attrs in [forms.py:10](shop/forms.py#L10), [:26](shop/forms.py#L26) are not applied |
| F20 | Low | [home.html:181-184](shop/templates/home.html#L181-L184) | Grid A4/A3/A2 pills are UI-only (JS at [:241](shop/templates/home.html#L241) just toggles a class); no add-to-cart from the grid |
| F21 | Low | [wishlist.html:39-42](shop/templates/wishlist.html#L39-L42) | Same non-functional pills, and unstyled: `.size-pill` CSS exists only in [home.html:32](shop/templates/home.html#L32) |
| F22 | Low | [base.html:232-234](shop/templates/base.html#L232-L234), [:268](shop/templates/base.html#L268) | Three footer social links are `href="#"`; "Request Exclusive Invite" is a button outside any form |
| F23 | Medium | whole project | No tests exist anywhere (`shop/tests.py` absent) |
| F24 | Low | [README.md](README.md), untracked files | "Not done yet" list is stale; `posterhub-loadtest.jmx` untracked; stray `source/` virtualenv |

---

## How this was verified

| Check | Result |
| --- | --- |
| `manage.py check` | clean (0 issues) |
| `manage.py makemigrations --check --dry-run` | "No changes detected", exit 0 — models and migrations agree |
| `manage.py showmigrations shop` | 0001–0003 all applied |
| Route sweep of every no-arg URL (anon + staff) | all resolve; exactly one page raises |
| Compile all 17 templates through the Django engine | 1 fails (`admin_order_detail.html`) |
| Render every page a real staff user can reach | 1 × HTTP 500 |
| `{% url %}` name cross-check (templates + Python) | no dangling names |
| Nested-`<form>` scan (all templates) | 0 |
| AST scan for unused imports / unreferenced defs | 3 unused imports, 1 dead form class |
| Response-context vs template-variable diff | 3 admin templates reference variables no view passes |
| Filter-registration scan | 1 undefined filter (`mul`) |
| `collectstatic --dry-run` (exit status captured without a pipe) | **fails, exit 1** |
| `check --deploy` | 6 security warnings |
| Fresh-clone check (`git archive HEAD` → run) | **`manage.py check` exit 1** |

---

## F1 — Critical: the committed revision cannot start

[views_admin.py:5](shop/views_admin.py#L5) does `from .forms import AddEditPosterForm`, but **`shop/forms.py` was never committed**: `git ls-tree -r HEAD` lists `shop/views_admin.py` and no `shop/forms.py`, while the file is untracked in the working tree.

Because [urls.py](shop/urls.py) imports `views_admin`, this breaks the root URLconf — **every page fails, not just the admin pages**:

```
$ git archive HEAD | tar -x -C <tmp> && cd <tmp> && python manage.py check
File ".../shop/views_admin.py", line 5, in <module>
    from .forms import AddEditPosterForm
ModuleNotFoundError: No module named 'shop.forms'
manage.py_check_exit=1
```

**Fix:** commit `shop/forms.py`. Add a smoke check (or the F23 test suite) so a commit whose URLconf cannot import never lands.

## F2 — High: `/manage/orders/<pk>/` returns HTTP 500

Four invalid constructs, each confirmed independently by compiling the expression alone:

| Line | Code | Why it fails |
| --- | --- | --- |
| [:20](shop/templates/admin_order_detail.html#L20) | `disabled="{{ order.status != 'Processing' }}"` | Django template expressions have no `!=`. Once rewritten, note that `disabled="False"` still disables the button — HTML boolean attributes care only about presence |
| [:40](shop/templates/admin_order_detail.html#L40), [:123](shop/templates/admin_order_detail.html#L123) | `{{ order.total:, }}` | Jinja2 thousands-separator syntax; Django has no `:,` filter |
| [:109](shop/templates/admin_order_detail.html#L109) | `{{ i.qty \| mul: i.price }}` | `mul` is not a registered filter, and there is no `shop/templatetags/` package |

`TemplateSyntaxError: Could not parse the remainder: ' != 'Processing''` is raised during template compilation, before any data is read.

## F3 — High: quantity editing is unreachable

The qty `<form>` ([:105](shop/templates/admin_order_detail.html#L105)) posts `action=save` and a number input but has **no submit control**, and the adjacent affordance is `<a href="#">Edit Qty →</a>` ([:111](shop/templates/admin_order_detail.html#L111)). The view's `action == "save"` branch ([views_admin.py:67-78](shop/views_admin.py#L67-L78)) therefore can never be triggered from the UI, so editing line-item quantities is effectively unimplemented.

## F4 — High: three blank KPI cards on `/manage/orders/`

The view computes `total_sales`, `processing_count` and `shipped_count` into local variables ([views_admin.py:103-105](shop/views_admin.py#L103-L105)) but passes only `{"orders": qs}` to the template, which renders `{{ total_sales }}` ([:20](shop/templates/admin_orders.html#L20)), `{{ processing_count }}` ([:28](shop/templates/admin_orders.html#L28)) and `{{ shipped_count }}` ([:32](shop/templates/admin_orders.html#L32)). Captured response context contains none of the three keys, so "Total sales" shows a bare `₹` and the other two cards render empty. No error is raised — the page looks fine and the numbers are simply absent.

## F5 — High: empty "Orders by status" card on `/manage/dashboard/`

[admin_dashboard.html:45](shop/templates/admin_dashboard.html#L45) iterates `{% for val, label in statuses %}`, but `statuses` is not in the context, so the loop body never executes. Verified against the served HTML: none of "Processing", "Shipped", "Delivered" or "Cancelled" appears inside that card.

## F6 — Medium: the status bars could never be non-zero

Even with F5 fixed, [:50](shop/templates/admin_dashboard.html#L50) and [:53](shop/templates/admin_dashboard.html#L53) address the context as `status_counts.val` / `status_colors.val` — a lookup for a *literal* key named `val`, not the loop variable. The view does supply `status_counts` and `status_colors` ([views_admin.py:119-120](shop/views_admin.py#L119-L120)), so only the template's indexing is wrong.

## F7 — Medium: phone validation never runs

[forms.py:22](shop/forms.py#L22) defines `OrderAdminForm` with a `clean_phone` validator ([:30](shop/forms.py#L30)), but nothing imports the class — the AST scan reports zero references project-wide. [views.py:100](shop/views.py#L100) stores `request.POST["phone"]` verbatim, so checkout accepts any string; the `pattern=` attribute in [checkout.html](shop/templates/checkout.html) is client-side only.

## F8 — Medium: coupons are display-only

[Coupon](shop/models.py#L58) is correct (including `is_available()`), and it is surfaced on the profile page ([profile.html:96-100](shop/templates/profile.html#L96-L100)) and counted on the dashboard — but `checkout.html` has no coupon input, `shop/views.py` never references `Coupon`, and `Order` has no discount column. Codes can be copied but never redeemed.

## F9 — Medium: password reset is unbranded and unreachable

`/accounts/password_reset/` returns 200 but is rendered by Django's **admin** templates — the served page title is `Password reset | Django site admin` and it contains no POSTERHUB chrome — because the project defines no `registration/password_reset_*.html`. `registration/logged_out.html` likewise resolves to admin's copy. The login page ([login.html](shop/templates/registration/login.html)) carries no "forgot password" link, so users cannot reach the flow at all.

## F10 — Medium: the `manage/` pages are undiscoverable

[base.html:177](shop/templates/base.html#L177) links staff to `/admin/` (Django's own admin) instead of the dashboard/posters/orders pages built for this project. Those routes exist and work, but nothing in the site chrome points at them.

## F11 — Medium: wasted query on `/manage/posters/`

`admin_posters` builds `categories = Poster.objects.order_by("-created")` and passes it in the context, but [admin_posters.html](shop/templates/admin_posters.html) never uses `categories` — it iterates `cats`. One unnecessary full-table query per page load.

## F12 — Medium: the project cannot be deployed

`collectstatic --dry-run` exits **1**:

```
django.core.exceptions.ImproperlyConfigured:
You're using the staticfiles app without having set the STATIC_ROOT setting to a filesystem path.
```

[settings.py:32](posterhub/settings.py#L32) sets `STATIC_URL` and `MEDIA_ROOT` but no `STATIC_ROOT`. (Re-run without a pipe — a piped `$?` reports the exit status of `tail`, not of `collectstatic`.)

## F13 — Medium: silent failure while editing quantity

[views_admin.py:77](shop/views_admin.py#L77) is a bare `pass` inside `except ValueError`. A malformed quantity is discarded without feedback and the request still redirects as if it succeeded.

## F14–F22 — Low

- **F14** Dead control: "Edit Qty →" is `href="#"` ([:111](shop/templates/admin_order_detail.html#L111)).
- **F15** Unused imports `Q`, `Category`, `OrderItem` ([forms.py:2-3](shop/forms.py#L2-L3)).
- **F16** `_grid.html` has no includers; `_art.html` is included only by `_grid.html` (line 4).
- **F17** Duplicate `total` assignment ([views_admin.py:93](shop/views_admin.py#L93), [:101](shop/views_admin.py#L101)).
- **F18** No `__str__` on `Wishlist`, `OrderItem`, `Review` ([models.py:24](shop/models.py#L24), [:41](shop/models.py#L41), [:73](shop/models.py#L73)).
- **F19** Admin poster forms render raw `{{ form.field }}` with no Tailwind classes, so they look nothing like the rest of the site.
- **F20** Grid size pills only toggle a CSS class ([home.html:181-184](shop/templates/home.html#L181-L184)); there is no add-to-cart from the grid.
- **F21** Wishlist pills are the same dead controls and are unstyled, because `.size-pill` is defined only in `home.html`'s `extra_head` ([home.html:32](shop/templates/home.html#L32)).
- **F22** Three footer social links are `href="#"` ([base.html:232-234](shop/templates/base.html#L232-L234)) and the newsletter button sits outside any form ([:268](shop/templates/base.html#L268)).

## F23 — Medium: no tests

No test module exists anywhere in the project. F1, F2, F4 and F5 are all the kind of defect a handful of view tests would have caught before commit.

## F24 — Low: stale docs and stray artifacts

[README.md](README.md) still lists image-upload UX and admin sales pages as unimplemented (both now exist) and omits the real gaps. `posterhub-loadtest.jmx` is untracked, and a second virtualenv sits at `source/` (Python 3.14, ignored by its own `.gitignore`).

---

## Verified complete and healthy

- `manage.py check` clean; models ↔ migrations in sync and applied (0001–0003).
- Every URL in the project resolves; no dangling `{% url %}` names in templates or Python.
- Auth gates behave correctly: `/manage/*` → 302 anonymous, 200 staff; `wishlist` / `cart` / `orders` / `profile` correct for both.
- The `manage/` prefix correctly avoids Django admin's catch-all view, which would otherwise swallow custom `admin/...` routes.
- Cart, checkout (server-side totals, order + item creation, confirmation email), order cancellation, purchase-gated reviews, wishlist toggle, profile stats and coupon listing all work end to end.
- 16 of 17 templates compile; zero nested `<form>` elements anywhere.

## Suggested fix order

1. **F1** — commit `shop/forms.py`; nothing else matters until the revision can boot.
2. **F2, F3** — repair `admin_order_detail.html` (four syntax errors, then a real submit control for quantities).
3. **F4, F5, F6** — pass the missing context and index the status dict correctly.
4. **F7, F11, F13, F15–F18** — delete or wire up the dead code.
5. **F8, F9, F10, F12, F23** — decide the unfinished features: coupons at checkout, branded password-reset templates plus a login link, `STATIC_ROOT`, navigation for the `manage/` pages, and a test suite.
