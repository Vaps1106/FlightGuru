"""Flight data providers. Each module exposes a ``search_*`` function that hits a
live API and a pure ``parse_*`` function (tested without network) that converts
the raw response into a list of normalized :class:`flightguru.models.Offer`.
"""
