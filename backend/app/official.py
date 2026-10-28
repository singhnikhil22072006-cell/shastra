"""Official AICTE verification adapter -- NOT IMPLEMENTED (deliberately).

No documented, authorised public API for validating approval letters is integrated.
Scraping the AICTE portal or guessing endpoints would produce unreliable results, so this
module always reports 'NOT_PERFORMED'. Once AICTE (or your SIH problem-statement owner)
grants API access or a data export, implement `verify()` here and keep the return shape.
"""


def verify(reference_no: str | None, institute_name: str | None) -> dict:
    return {
        "status": "NOT_PERFORMED",
        "supported": False,
        "reason": (
            "Official verification against AICTE records is not supported in this build. "
            "Nothing in this report confirms that the document is genuine or that the "
            "institution is currently approved."
        ),
    }
