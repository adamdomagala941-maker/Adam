import unittest

import fitz

from backend.pictograms import ASSETS, detect_pdf_pictograms


def pdf_with_icons(codes, size=45, heading='2.2 Label elements', section_end=True):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((40, 40), heading)
    for i, code in enumerate(codes):
        with fitz.open(stream=(ASSETS / (code+'.svg')).read_bytes(), filetype='svg') as svg:
            with fitz.open('pdf', svg.convert_to_pdf()) as icon:
                x=40+i*(size+8)
                page.show_pdf_page(fitz.Rect(x, 65, x+size, 65+size), icon, 0)
    if section_end:
        page.insert_text((40, 180), '2.3 Other hazards')
    content=doc.tobytes()
    doc.close()
    return content


class PictogramTests(unittest.TestCase):
    def test_all_nine_standard_symbols(self):
        for n in range(1, 10):
            code=f'GHS{n:02}'
            with self.subTest(code=code):
                self.assertEqual(detect_pdf_pictograms(pdf_with_icons([code])), [code])

    def test_small_symbols_and_multiple(self):
        self.assertEqual(detect_pdf_pictograms(pdf_with_icons(['GHS02','GHS05','GHS07'],size=25)), ['GHS02','GHS05','GHS07'])

    def test_non_labeling_page_not_classified(self):
        self.assertEqual(detect_pdf_pictograms(pdf_with_icons(['GHS02'],heading='Promotional logo')), [])

    def test_original_label_composite(self):
        doc=fitz.open();page=doc.new_page()
        page.insert_text((40,40),'2.2 Label elements')
        page.insert_image(fitz.Rect(40,65,180,205),filename=str(ASSETS/'current_ghs.png'))
        page.insert_text((40,230),'2.3 Other hazards')
        self.assertEqual(detect_pdf_pictograms(doc.tobytes()),['GHS02','GHS05','GHS07'])
        doc.close()

    def test_symbols_after_labeling_section_ignored(self):
        doc=fitz.open();page=doc.new_page()
        page.insert_text((40,40),'2.2 Label elements')
        page.insert_text((40,60),'2.3 Other hazards')
        page.insert_image(fitz.Rect(40,80,180,220),filename=str(ASSETS/'current_ghs.png'))
        self.assertEqual(detect_pdf_pictograms(doc.tobytes()),[])
        doc.close()

    def test_red_rectangle_not_classified(self):
        doc=fitz.open();page=doc.new_page();page.insert_text((40,40),'2.2 Label elements')
        page.draw_rect(fitz.Rect(40,70,90,120),color=(1,0,0),width=4)
        page.insert_text((55,100),'!')
        self.assertEqual(detect_pdf_pictograms(doc.tobytes()),[])
        doc.close()

    def test_unrecognized_diamond_not_classified(self):
        doc=fitz.open();page=doc.new_page();page.insert_text((40,40),'2.2 Label elements')
        shape=page.new_shape();shape.draw_polyline([(65,65),(90,90),(65,115),(40,90),(65,65)]);shape.finish(color=(1,0,0),width=3);shape.commit()
        page.draw_circle((65,90),10,color=(0,0,0),fill=(0,0,0))
        self.assertEqual(detect_pdf_pictograms(doc.tobytes()),[])
        doc.close()

    def test_invalid_document(self):
        self.assertEqual(detect_pdf_pictograms(b'%PDF-broken'),[])
        self.assertEqual(detect_pdf_pictograms(b'not a PDF'),[])


if __name__ == '__main__':
    unittest.main()
