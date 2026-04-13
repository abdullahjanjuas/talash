# Parsing CVs:
#   pdfplumber runs FIRST on each page to detect tables and their locations
#   PyMuPDF runs SECOND but clips out the table bounding boxes
#   Result: body text comes from PyMuPDF, tables come from pdfplumber: no overlap

import fitz          # PyMuPDF
import pdfplumber


def parse_cv(pdf_path: str) -> dict:
    """
    Master parse function. Processes the PDF page by page.
    For each page:
      - pdfplumber detects tables and records WHERE they are on the page
      - PyMuPDF extracts text but EXCLUDES those table regions
      - pdfplumber provides the clean structured version of those tables

    This way every piece of content appears exactly once.
    """

    all_pages_text = []   # will hold processed text for each page
    all_tables = []       # raw table data for debugging/reference

    # Open the same PDF in both libraries simultaneously
    fitz_doc = fitz.open(pdf_path)

    with pdfplumber.open(pdf_path) as plumber_pdf:

        # Process page by page: both libraries use the same page index
        for page_num in range(len(fitz_doc)):

            fitz_page = fitz_doc[page_num]
            plumber_page = plumber_pdf.pages[page_num]

            # Step 1: Ask pdfplumber where tables are on this page and create bounding boxes
            detected_tables = plumber_page.find_tables()

            # Collect the bounding boxes of all tables on this page
            # We will use these to exclude those regions from PyMuPDF extraction
            table_bboxes = []
            for table_obj in detected_tables:
                bbox = table_obj.bbox  # (x0, top, x1, bottom) in PDF points
                table_bboxes.append(bbox)

            # Step 2: Extract body text using PyMuPDF, skipping table areas
            if table_bboxes:  # In case there are tables in cv
                blocks = fitz_page.get_text("blocks")
                body_text_parts = []

                for block in blocks:
                    if block[6] != 0:
                        # block_type 1 = image block, skip entirely
                        continue

                    # block coordinates: x0=block[0], y0=block[1], x1=block[2], y1=block[3]
                    block_x0, block_y0, block_x1, block_y1 = block[0], block[1], block[2], block[3]
                    block_text = block[4]

                    # Check if this text block overlaps with any table bounding box
                    overlaps_table = False
                    for (tab_x0, tab_top, tab_x1, tab_bottom) in table_bboxes:
                        # Two rectangles overlap if they overlap on BOTH axes
                        no_overlap = (
                            block_x1 < tab_x0 or   # block is entirely left of table
                            block_x0 > tab_x1 or   # block is entirely right of table
                            block_y1 < tab_top or  # block is entirely above table
                            block_y0 > tab_bottom  # block is entirely below table
                        )
                        if not no_overlap:
                            overlaps_table = True
                            break   # no need to check other tables

                    if not overlaps_table:
                        # This text block is NOT in a table region — keep it
                        body_text_parts.append(block_text.strip())

                body_text = "\n".join(body_text_parts)

            else:
                # No tables on this page so extract normally
                body_text = fitz_page.get_text()

            # Step 3: Get the clean structured table text from pdfplumber
            # Now extract the actual table data from pdfplumber for the
            # regions we just skipped in PyMuPDF.
            table_text_parts = []

            for table_obj in detected_tables:
                # extract() gives us the table as a list of rows
                # Each row is a list of cell values
                rows = table_obj.extract()
                all_tables.append(rows)  # save for reference

                if not rows:
                    continue

                # Convert the structured table into a readable text format
                table_lines = []
                for row in rows:
                    if row:
                        # Replace None cells with empty string
                        cleaned_cells = [str(cell).strip() if cell else "" for cell in row]
                        table_lines.append(" | ".join(cleaned_cells))

                table_text_parts.append(
                    f"\n[TABLE START]\n" +
                    "\n".join(table_lines) +
                    "\n[TABLE END]\n"
                )

            # Step 4: Assemble this page's final text
            # Body text first, then tables
            page_final_text = f"\n--- Page {page_num + 1} ---\n"
            page_final_text += body_text.strip()
            if table_text_parts:
                page_final_text += "\n" + "\n".join(table_text_parts)

            all_pages_text.append(page_final_text)

    fitz_doc.close()

    full_text = "\n".join(all_pages_text)

    return {
        "text": full_text,
        "tables": all_tables,
        "char_count": len(full_text),
        "pages": len(all_pages_text)
    }
    
if __name__ == "__main__":
    print("Running parser test...")

    test_pdf = "M. Abdullah Janjua_CV.pdf"   # change this

    try:
        result = parse_cv(test_pdf)

        print("\n✅ PARSING SUCCESSFUL\n")

        print("----- FULL TEXT OUTPUT -----\n")
        print(result["text"])   # ✅ FULL CV TEXT

        print("\n----- METADATA -----")
        print(f"Pages: {result['pages']}")
        print(f"Characters: {result['char_count']}")

    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")