from fpdf import FPDF
import datetime

class ReportGenerator(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'Network Security Report', 0, 1, 'C')
        self.ln(20)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

def generate_pdf(scan_results):
    pdf = ReportGenerator()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    pdf.cell(200, 10, txt=f"Scan Date: {datetime.datetime.now()}", ln=1, align='L')
    pdf.ln(10)
    
    for host in scan_results:
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(200, 10, txt=f"Host: {host['ip']} ({host.get('hostnames', [''])[0]})", ln=1)
        pdf.set_font("Arial", size=11)
        pdf.cell(200, 10, txt=f"MAC: {host.get('mac', 'N/A')} - Vendor: {host.get('vendor', 'N/A')}", ln=1)
        
        if 'ports' in host:
            pdf.ln(5)
            pdf.cell(200, 10, txt="Open Ports:", ln=1)
            for port, info in host['ports'].items():
                 pdf.cell(200, 10, txt=f"  - Port {port}: {info['name']} ({info['state']})", ln=1)
        
        pdf.ln(10)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(10)

    filename = f"report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    pdf.output(filename)
    return filename
