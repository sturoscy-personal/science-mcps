def ev_adoption_heatmap(index_id: str, min_year: int = 2010, max_year: int = 2027):
    """
    Query a Globus Search index containing EV registration records and aggregate
    counts by county and model year, returning heatmap-ready data.

    Parameters
    ----------
    index_id : str
        UUID of the Globus Search index holding the EV registration data.
    min_year : int
        Earliest model year to include (default 2010).
    max_year : int
        Latest model year to include (default 2027).

    Returns
    -------
    dict with keys:
        index_id      - the queried index
        min_year      - lower year bound applied
        max_year      - upper year bound applied
        total_records - number of records included in the aggregation
        counties      - sorted list of county names found
        rows          - list of {"county", "model_year", "count"} dicts,
                        sorted by county then year — ready for a pivot/heatmap
    """
    import globus_sdk
    from collections import defaultdict

    client = globus_sdk.SearchClient()

    county_year_counts = defaultdict(lambda: defaultdict(int))
    offset = 0
    limit = 100

    while True:
        response = client.post_search(
            index_id,
            {"q": "*", "limit": limit, "offset": offset},
        )
        hits = response.get("gmeta", [])
        if not hits:
            break

        for hit in hits:
            content = hit["entries"][0]["content"]
            county = content.get("county", "Unknown")
            year = content.get("model_year")
            if year and min_year <= year <= max_year:
                county_year_counts[county][year] += 1

        offset += limit
        if offset >= response.get("total", 0):
            break

    rows = [
        {"county": county, "model_year": year, "count": count}
        for county, years in sorted(county_year_counts.items())
        for year, count in sorted(years.items())
    ]

    return {
        "index_id": index_id,
        "min_year": min_year,
        "max_year": max_year,
        "total_records": sum(r["count"] for r in rows),
        "counties": sorted(county_year_counts.keys()),
        "rows": rows,
    }
