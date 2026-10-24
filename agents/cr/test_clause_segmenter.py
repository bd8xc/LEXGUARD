from processing.document_processor import DocumentProcessor
from processing.clause_segmenter import ClauseSegmenter


##############################################################
# FILE
##############################################################

FILE_PATH = (
    "sample_contracts/contract.pdf"
)


##############################################################
# PROCESS DOCUMENT
##############################################################

processor = DocumentProcessor()

document = processor.process(
    FILE_PATH
)


##############################################################
# SEGMENT CLAUSES
##############################################################

segmenter = ClauseSegmenter()

clauses = segmenter.segment(
    document["text"]
)


##############################################################
# RESULTS
##############################################################

print(
    "=" * 70
)

print(
    "CLAUSE SEGMENTATION TEST"
)

print(
    "=" * 70
)

print(
    f"\nDocument : "
    f"{document['file_name']}"
)

print(
    f"Clauses  : "
    f"{len(clauses)}"
)

print()


##############################################################
# PRINT EVERY CLAUSE
##############################################################

for clause in clauses:

    print(
        "-" * 70
    )

    print(
        f"Index   : "
        f"{clause['index']}"
    )

    print(
        f"Number  : "
        f"{clause['clause_number']}"
    )

    print(
        f"Section : "
        f"{clause['section']}"
    )

    print(
        f"Heading : "
        f"{clause['heading']}"
    )

    print(
        "\nText:"
    )

    print(
        clause["text"]
    )

    print()


##############################################################
# SUMMARY
##############################################################

print(
    "=" * 70
)

print(
    f"TOTAL CLAUSES: "
    f"{len(clauses)}"
)

print(
    "=" * 70
)