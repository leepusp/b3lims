from django.test import SimpleTestCase

from core.services.jupyter_documents import (
    JupyterNotebookError,
    MAX_CELLS,
    normalize_notebook,
)


class JupyterDocumentTests(SimpleTestCase):
    def test_normalize_notebook_preserves_safe_output(self):
        notebook = normalize_notebook(
            {
                "cells": [
                    {
                        "cell_type": "code",
                        "metadata": {},
                        "source": ["print(42)\\n"],
                        "execution_count": 1,
                        "outputs": [
                            {
                                "output_type": "display_data",
                                "metadata": {},
                                "data": {
                                    "text/plain": ["42"],
                                    "text/html": [
                                        "<script>alert(1)</script>"
                                    ],
                                },
                            }
                        ],
                    }
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            }
        )

        self.assertEqual(len(notebook["cells"]), 1)
        self.assertEqual(
            notebook["cells"][0]["cell_type"],
            "code",
        )

        output_data = (
            notebook["cells"][0]["outputs"][0]["data"]
        )

        self.assertIn("text/plain", output_data)
        self.assertNotIn("text/html", output_data)

    def test_normalize_notebook_rejects_excess_cells(self):
        notebook = {
            "cells": [
                {
                    "cell_type": "markdown",
                    "metadata": {},
                    "source": [],
                }
                for _ in range(MAX_CELLS + 1)
            ],
            "metadata": {},
            "nbformat": 4,
            "nbformat_minor": 5,
        }

        with self.assertRaises(JupyterNotebookError):
            normalize_notebook(notebook)
