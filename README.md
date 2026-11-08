# Udyam Digital prototype

A self-contained, local web prototype based on the Udyam Digital solution deck and the supplied synthetic dataset. It includes:

- A lead-funnel dashboard derived from `smb_leads.csv`.
- A rule-based business advisor and quote that reads `product_catalogue.csv`.
- A consent-first GSTIN/Udyam lookup against the supplied mock registries, with masked identifiers.
- A temporary, in-memory sample order tracker.
- A transparent sample lead-priority queue that does not expose contact details.

The server is in the project root, CSV data is in `data/`, and browser assets are in `static/`.

## Requirements

- Python 3.9 or later
- A modern browser
- No third-party Python packages or internet connection required to run the application

## Run on Windows

1. Extract the project ZIP.
2. Double-click `start.bat`, or open PowerShell in this folder and run:

   ```powershell
   python server.py
   ```

3. Open <http://127.0.0.1:8000>.
4. To stop the server, press `Ctrl+C` in the terminal.

If port 8000 is in use, change `PORT` near the top of `server.py`.

## Suggested walkthrough

1. Start on **Overview** and point out the data-backed funnel and baseline metrics.
2. Open **Advisor & quote**, keep the professional-office example or try another segment, and generate a catalogue-backed quote.
3. Open **Smart KYC**, check the consent box, and look up a GSTIN or Udyam number from the supplied registry CSVs.
4. Return to the quote and continue to **Order tracker** to create a temporary sample order.
5. Finish on **Field handoff** to show an explainable priority queue with no contact details.

## Run tests

```powershell
python -m unittest -v test_prototype
```
