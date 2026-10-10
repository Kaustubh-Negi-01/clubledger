# ClubLedger

Single-club ledger and operational system for Skyline Student Association.

## Requirements
- Python 3.12+

## Setup Instructions

1. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -e .
   ```

3. Run migrations:
   ```bash
   python -m clubledger.cli migrate
   ```

4. Run unit tests:
   ```bash
   python -m pytest tests/unit/core/
   ```
