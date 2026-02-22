from pocketflow import AsyncFlow
from app.nodes.scanner import ScannerNode
from app.nodes.ecosystem import EcosystemDetectionNode
from app.nodes.analysis import AnalysisNode
from app.nodes.remediation import RemediationNode
from app.nodes.verification import VerificationNode
from app.nodes.reporting import ReportingNode

class GuardianFlow(AsyncFlow):
    def __init__(self):
        super().__init__()
        self.scanner = ScannerNode()
        self.ecosystem = EcosystemDetectionNode()
        self.analysis = AnalysisNode()
        self.remediation = RemediationNode()
        self.verification = VerificationNode()
        self.reporting = ReportingNode()
        self.scanner >> self.ecosystem
        self.ecosystem >> self.analysis
        self.analysis >> self.remediation
        self.remediation >> self.verification
        self.verification - "success" >> self.reporting
        self.verification - "failed" >> self.remediation
        self.start(self.scanner)
