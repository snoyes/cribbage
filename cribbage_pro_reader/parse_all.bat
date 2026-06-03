for %%f in (data\*.zip) do @if not exist "data\%%~nf.json" python reader.py "%%f"
