# Frontend: what people see and interact with

Start with `templates/base.html`, `templates/dashboard.html`, `static/app.css` and `static/app.js`.

- **HTML** describes headings, forms, buttons and tables.
- **Jinja** fills HTML with server-provided values. `{{ value }}` displays a value; `{% if ... %}` selects content; `{% for ... %}` repeats content; `{# ... #}` is a developer comment.
- **CSS** controls colour, spacing, responsive layout and animation.
- **JavaScript** handles small browser interactions: mobile menu, submission feedback, confirmations and payment-result confetti.

This is a server-rendered app. There is no separate React application, Node frontend server or client-side database. The backend sends complete HTML pages; normal HTML forms submit back to it.

## Folders

| Path | Contents |
| --- | --- |
| `templates/base.html` | Shared navigation, page heading and CSS/JS links |
| `templates/dashboard.html` | Overview with real club data |
| `templates/auth/` | Sign-in and registration |
| `templates/membership/` | Joining, member cards and verification |
| `templates/events/` | Events, tickets, check-in and event report |
| `templates/store/` | Catalog, product details and orders |
| `templates/payments/` | Simulator checkout, result popup and officer payment list |
| `templates/finance/` | Accounts, journal entries and integrity results |
| Remaining templates | Named operational pages, such as expenses, tasks, announcements and close |
| `static/app.css` | Shared visual design and responsive rules |
| `static/page-layouts.css` | Page-specific rules extracted from former inline styles |
| `static/app.js` | Readable browser behavior; no embedded HTML event handlers |
| `static/campus-pass.svg` | Original dashboard illustration |
| `static/fonts/` | Local Space Grotesk font and its license |
| `static/vendor/` | Third-party HTMX source and license; not loaded by the current base template |

`__init__.py` is only a resource-package marker so installation can include the assets. It does not run a frontend server.

Changing a price shown in HTML cannot change the charged amount: the backend calculates prices and enforces permissions.
