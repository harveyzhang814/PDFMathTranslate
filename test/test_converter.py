import unittest
from unittest.mock import Mock, patch, MagicMock
from pdfminer.layout import LTPage, LTChar, LTLine
from pdfminer.pdfinterp import PDFResourceManager
from pdf2zh.converter import PDFConverterEx, TranslateConverter


class TestPDFConverterEx(unittest.TestCase):
    def setUp(self):
        self.rsrcmgr = PDFResourceManager()
        self.converter = PDFConverterEx(self.rsrcmgr)

    def test_begin_page(self):
        mock_page = Mock()
        mock_page.pageno = 1
        mock_page.cropbox = (0, 0, 100, 200)
        mock_ctm = [1, 0, 0, 1, 0, 0]
        self.converter.begin_page(mock_page, mock_ctm)
        self.assertIsNotNone(self.converter.cur_item)
        self.assertEqual(self.converter.cur_item.pageid, 1)

    def test_render_char(self):
        mock_matrix = (1, 2, 3, 4, 5, 6)
        mock_font = Mock()
        mock_font.to_unichr.return_value = "A"
        mock_font.char_width.return_value = 10
        mock_font.char_disp.return_value = (0, 0)
        graphic_state = Mock()
        self.converter.cur_item = Mock()
        result = self.converter.render_char(
            mock_matrix,
            mock_font,
            fontsize=12,
            scaling=1.0,
            rise=0,
            cid=65,
            ncs=None,
            graphicstate=graphic_state,
        )
        self.assertEqual(result, 120.0)  # Expected text width


class TestTranslateConverter(unittest.TestCase):
    def setUp(self):
        self.rsrcmgr = PDFResourceManager()
        self.layout = {1: Mock()}
        self.translator_class = Mock()
        self.converter = TranslateConverter(
            self.rsrcmgr,
            layout=self.layout,
            lang_in="en",
            lang_out="zh",
            service="google",
        )

    def test_translator_initialization(self):
        self.assertIsNotNone(self.converter.translator)
        self.assertEqual(self.converter.translator.lang_in, "en")
        self.assertEqual(self.converter.translator.lang_out, "zh-CN")

    @patch("pdf2zh.converter.TranslateConverter.receive_layout")
    def test_receive_layout(self, mock_receive_layout):
        mock_page = LTPage(1, (0, 0, 100, 200))
        mock_font = Mock()
        mock_font.fontname.return_value = "mock_font"
        mock_page.add(
            LTChar(
                matrix=(1, 2, 3, 4, 5, 6),
                font=mock_font,
                fontsize=12,
                scaling=1.0,
                rise=0,
                text="A",
                textwidth=10,
                textdisp=(1.0, 1.0),
                ncs=Mock(),
                graphicstate=Mock(),
            )
        )
        self.converter.receive_layout(mock_page)
        mock_receive_layout.assert_called_once_with(mock_page)

    def test_receive_layout_with_complex_formula(self):
        ltpage = LTPage(1, (0, 0, 500, 500))
        ltchar = Mock()
        ltchar.fontname.return_value = "mock_font"
        ltline = LTLine(0.1, (0, 0), (10, 20))
        ltpage.add(ltchar)
        ltpage.add(ltline)
        mock_layout = MagicMock()
        mock_layout.shape = (100, 100)
        mock_layout.__getitem__.return_value = -1
        self.converter.layout = [None, mock_layout]
        self.converter.thread = 1
        result = self.converter.receive_layout(ltpage)
        self.assertIsNotNone(result)

    def test_invalid_translation_service(self):
        with self.assertRaises(ValueError):
            TranslateConverter(
                self.rsrcmgr,
                layout=self.layout,
                lang_in="en",
                lang_out="zh",
                service="InvalidService",
            )


class TestDropCapCascade(unittest.TestCase):
    """Regression tests for the drop cap → intermediate size → body text cascade bug.

    Bug: a paragraph starting with a large drop cap ('A', ~30pt) followed by an
    intermediate-sized char ('S', ~15pt) caused all body text (~10pt) to be
    incorrectly classified as subscript/formula, resulting in text overlap in
    the translated PDF.

    Fix: `drop_cap_cascade` flag allows the reference size to settle through one
    extra downward update after a len==1 downward update; subscript detection is
    suppressed while the flag is active.
    """

    def _make_char(self, text, size, x0, x1, y0, y1, fontname="Times-Roman"):
        """Create a minimal LTChar-like Mock for receive_layout tests."""
        ch = Mock()
        ch.get_text.return_value = text
        ch.size = size
        ch.x0 = x0
        ch.x1 = x1
        ch.y0 = y0
        ch.y1 = y1
        ch.fontname = fontname
        ch.matrix = (1, 0, 0, 1, x0, y0)  # matrix[0]=1, matrix[3]=1 (horizontal)
        ch.cid = ord(text[0]) if text else 0
        ch.width = x1 - x0
        return ch

    def _run_paragraph_build(self, chars, page_width=500, page_height=500):
        """Simulate the receive_layout paragraph-building loop.

        Returns (sstk, pstk, var) — the paragraph text stack, paragraph attribute
        stack, and formula-group stack — after processing all chars.
        """
        import re, unicodedata, numpy as np
        from dataclasses import dataclass

        @dataclass
        class P:
            y: float; x: float; x0: float; x1: float
            y0: float; y1: float; size: float; brk: bool

        # Uniform layout: everything is cls=3 (same text block)
        layout = np.full((page_height, page_width), 3)

        def vflag(font, char):
            if isinstance(font, bytes):
                try: font = font.decode()
                except: font = ""
            font = font.split("+")[-1]
            if re.match(r"\(cid:", char): return True
            if re.match(r"(CM[^R]|MS.M|XY|MT|BL|RM|EU|LA|RS|LINE|LCIRCLE|TeX-|rsfs|txsy|wasy|stmary|.*Mono|.*Code|.*Sym|.*Math)", font): return True
            if char and char != " " and (
                unicodedata.category(char[0]) in ["Lm","Mn","Sk","Sm","Zl","Zp","Zs"]
                or ord(char[0]) in range(0x370, 0x400)
            ): return True
            return False

        sstk, pstk, vstk, var = [], [], [], []
        vbkt, vfix = 0, 0
        xt, xt_cls = None, -1
        vmax = page_width / 4
        drop_cap_cascade = False

        for child in chars:
            cur_v = False
            h, w = layout.shape
            cx = int(np.clip(child.x0, 0, w - 1))
            cy = int(np.clip(child.y0, 0, h - 1))
            cls = layout[cy, cx]

            _is_subscript = (
                cls == xt_cls and len(sstk[-1].strip()) > 1
                and child.size < pstk[-1].size * 0.79
                and not drop_cap_cascade
            ) if pstk else False

            if cls == 0 or _is_subscript or vflag(child.fontname, child.get_text()) or (child.matrix[0] == 0 and child.matrix[3] == 0):
                cur_v = True

            if not cur_v:
                if vstk and child.get_text() == "(":
                    cur_v = True; vbkt += 1
                if vbkt and child.get_text() == ")":
                    cur_v = True; vbkt -= 1

            if not cur_v or cls != xt_cls or (sstk and sstk[-1] != "" and abs(child.x0 - xt.x0) > vmax):
                if vstk:
                    if not cur_v and cls == xt_cls and child.x0 > max(v.x0 for v in vstk):
                        vfix = vstk[0].y0 - child.y0
                    if sstk and sstk[-1] == "":
                        xt_cls = -1
                    sstk[-1] += f"{{v{len(var)}}}"
                    var.append(vstk)
                    vstk = []; vfix = 0

            if not vstk:
                if cls == xt_cls:
                    if child.x0 > xt.x1 + 1: sstk[-1] += " "
                    elif child.x1 < xt.x0: sstk[-1] += " "; pstk[-1].brk = True
                else:
                    sstk.append("")
                    pstk.append(P(child.y0, child.x0, child.x0, child.x0, child.y0, child.y1, child.size, False))
                    drop_cap_cascade = False

            if not cur_v:
                is_len1 = len(sstk[-1].strip()) == 1
                if ((child.size > pstk[-1].size and child.size < pstk[-1].size * 1.3)
                        or is_len1 or drop_cap_cascade) and child.get_text() != " ":
                    old_size = pstk[-1].size
                    pstk[-1].y -= child.size - old_size
                    pstk[-1].size = child.size
                    drop_cap_cascade = is_len1 and child.size < old_size
                elif child.get_text() != " ":
                    drop_cap_cascade = False
                sstk[-1] += child.get_text()
            else:
                if not vstk and cls == xt_cls and child.x0 > xt.x0:
                    vfix = child.y0 - xt.y0
                vstk.append(child)

            if pstk:
                pstk[-1].x0 = min(pstk[-1].x0, child.x0)
                pstk[-1].x1 = max(pstk[-1].x1, child.x1)
                pstk[-1].y0 = min(pstk[-1].y0, child.y0)
                pstk[-1].y1 = max(pstk[-1].y1, child.y1)

            xt = child; xt_cls = cls

        if vstk:
            sstk[-1] += f"{{v{len(var)}}}"
            var.append(vstk)

        return sstk, pstk, var

    def test_drop_cap_cascade_body_text_not_formula(self):
        """Body text after drop-cap → intermediate-size chain must not be formula.

        Scenario from A3_Bitner_1990_ServiceEncounters.pdf page 0:
          - 'A' at 29.82pt (drop cap, Helvetica)
          - 'S' at 15.68pt (Times-Roman, small-caps opening of word "Service")
          - 'e','r','v','i','c','e' at 10.58pt (Times-Roman, body text)
        Before fix: body text chars were flagged as subscript → formula groups
        After fix: body text chars go into the paragraph text directly
        """
        chars = [
            self._make_char('A', 29.82, 46, 64, 350, 380, fontname='Helvetica'),
            self._make_char('S', 15.68, 68, 78, 350, 366, fontname='Times-Roman'),
            self._make_char('e', 10.58, 79, 85, 350, 361, fontname='Times-Roman'),
            self._make_char('r', 10.58, 86, 91, 350, 361, fontname='Times-Roman'),
            self._make_char('v', 10.58, 92, 98, 350, 361, fontname='Times-Roman'),
            self._make_char('i', 10.58, 99, 102, 350, 361, fontname='Times-Roman'),
            self._make_char('c', 10.58, 103, 109, 350, 361, fontname='Times-Roman'),
            self._make_char('e', 10.58, 110, 116, 350, 361, fontname='Times-Roman'),
        ]
        sstk, pstk, var = self._run_paragraph_build(chars)

        # Should produce exactly 1 paragraph with no formula groups
        self.assertEqual(len(sstk), 1, "Expected exactly 1 paragraph")
        self.assertEqual(len(var), 0, "Expected 0 formula groups — body text must not be classified as subscript/formula")
        # Paragraph text should contain the body text chars
        para_text = sstk[0]
        for ch in 'Service':
            self.assertIn(ch, para_text, f"'{ch}' should be in paragraph text, not a formula group")
        # Paragraph reference size should settle to body text size (~10.58)
        self.assertAlmostEqual(pstk[0].size, 10.58, places=1,
            msg="Paragraph reference size should settle to body text size after cascade")

    def test_drop_cap_two_level_no_cascade(self):
        """Drop cap directly followed by body text (two-level, no cascade needed)."""
        chars = [
            self._make_char('A', 30.0, 46, 64, 350, 380, fontname='Helvetica'),
            self._make_char('n', 10.5, 65, 72, 350, 361, fontname='Times-Roman'),
            self._make_char('d', 10.5, 73, 80, 350, 361, fontname='Times-Roman'),
        ]
        sstk, pstk, var = self._run_paragraph_build(chars)
        self.assertEqual(len(var), 0, "Body text after drop cap must not be formula")
        self.assertAlmostEqual(pstk[0].size, 10.5, places=1)

    def test_actual_subscript_still_detected(self):
        """True subscripts (at non-drop-cap positions) must still be detected.

        Subscript detection requires len(sstk[-1].strip()) > 1, i.e. the
        candidate char must be after at least 2 prior text chars.  Here we put
        the subscript '2' at position 5 (after 'H','e','l','l','o').
        """
        base = 10.5
        sub  = 7.5  # 7.5 / 10.5 = 0.714 < 0.79
        chars = [
            self._make_char('H', base, 10, 17, 350, 361),
            self._make_char('e', base, 18, 24, 350, 361),
            self._make_char('l', base, 25, 29, 350, 361),
            self._make_char('l', base, 30, 34, 350, 361),
            self._make_char('o', base, 35, 42, 350, 361),
            self._make_char('2', sub,  43, 48, 347, 356),  # subscript
            self._make_char('O', base, 49, 57, 350, 361),
        ]
        sstk, pstk, var = self._run_paragraph_build(chars)
        total_formula_chars = sum(len(v) for v in var)
        self.assertGreater(total_formula_chars, 0,
            "True subscript '2' at position 5 should be detected as formula")


if __name__ == "__main__":
    unittest.main()
