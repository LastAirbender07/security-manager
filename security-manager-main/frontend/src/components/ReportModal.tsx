import { useState, useEffect } from 'react';
import { getScanReport, ScanReport } from '../api/client';

interface ReportModalProps {
    scanId: number;
    onClose: () => void;
}

export const ReportModal = ({ scanId, onClose }: ReportModalProps) => {
    const [report, setReport] = useState<ScanReport | null>(null);
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState('overview');
    const [expandedFix, setExpandedFix] = useState<number | null>(null);
    const [codeView, setCodeView] = useState<'before' | 'after'>('after');

    useEffect(() => {
        getScanReport(scanId)
            .then((data) => setReport(data))
            .catch(() => setReport(null))
            .finally(() => setLoading(false));
    }, [scanId]);

    const r = report?.report || {};
    const vulns = r.scanner?.vulnerabilities || [];
    const libs = r.scanner?.detected_libraries || {};
    const eco = r.ecosystem;
    const remediations = r.remediation || [];
    const verifications = r.verification || [];
    const verifiedCount = verifications.filter(v => v.verified).length;

    const tabs = [
        { id: 'overview', icon: '📊', label: 'Overview' },
        { id: 'scanner', icon: '🔍', label: 'Findings', count: vulns.length },
        { id: 'ecosystem', icon: '⚙️', label: 'Environment' },
        { id: 'remediation', icon: '🛡️', label: 'Code Changes', count: remediations.length },
        { id: 'verification', icon: '✅', label: 'Verification', count: verifications.length },
    ];

    const severityIcon = (sev: string) => {
        switch (sev?.toUpperCase()) {
            case 'CRITICAL': return '🔴';
            case 'HIGH': return '🟠';
            case 'MEDIUM': return '🟡';
            case 'LOW': return '🟢';
            default: return '⚪';
        }
    };

    const getFileExt = (path: string) => {
        const ext = path.split('.').pop()?.toLowerCase() || '';
        return ext;
    };

    const getLangIcon = (path: string) => {
        const ext = getFileExt(path);
        switch (ext) {
            case 'py': return '🐍';
            case 'js': case 'ts': case 'jsx': case 'tsx': return '📜';
            case 'java': return '☕';
            case 'go': return '🔵';
            case 'rb': return '💎';
            default: return '📄';
        }
    };

    const parsedTests = (output: string) => {
        const lines = output.split('\n');
        const tests: { name: string; status: string; details?: string }[] = [];

        lines.forEach(line => {
            // Match FAIL: test_name (class)
            const failMatch = line.match(/^(FAIL|ERROR):\s+(\w+)/);
            if (failMatch) {
                tests.push({ name: failMatch[2], status: 'FAIL' });
            }
            // Match success if verbose (ok) - harder without verbose output
        });

        // Heuristic: if we see "Ran N tests in Xs", we might assume others passed if N > fails.
        // But for now, let's just show explicit failures.
        // If NO explicit failures found but output contains "OK", maybe show "All tests passed"

        // Actually, let's try to find the "test_name ... FAIL" pattern too if it exists
        // User output: FAIL: test_command_injection_prevention (__main__...)

        if (tests.length === 0 && output.includes('OK')) {
            tests.push({ name: 'All Tests', status: 'PASS', details: 'Full suite passed' });
        }

        return tests;
    };

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="report-modal" onClick={(e) => e.stopPropagation()}>
                {/* Header */}
                <div className="report-header">
                    <div className="report-header-left">
                        <div className="report-title-row">
                            <span className="report-icon">📋</span>
                            <div>
                                <h3 className="report-title">Security Report <span className="report-scan-id">#{scanId}</span></h3>
                                {report && <div className="report-repo-url">{report.repo}</div>}
                            </div>
                        </div>
                    </div>
                    <button className="modal-close" onClick={onClose}>✕</button>
                </div>

                {loading ? (
                    <div className="report-loading">
                        <div className="report-spinner"></div>
                        <span>Analyzing report data...</span>
                    </div>
                ) : !report || !report.report || Object.keys(report.report).length === 0 ? (
                    <div className="report-empty-state">
                        <span className="report-empty-icon">📭</span>
                        <h4>No Report Data</h4>
                        <p>This scan hasn't generated report data yet. Try running a new scan.</p>
                    </div>
                ) : (
                    <>
                        {/* Tab Navigation */}
                        <div className="report-tabs">
                            {tabs.map((tab) => (
                                <button
                                    key={tab.id}
                                    className={`report-tab ${activeTab === tab.id ? 'active' : ''}`}
                                    onClick={() => setActiveTab(tab.id)}
                                >
                                    <span className="tab-icon">{tab.icon}</span>
                                    <span className="tab-label">{tab.label}</span>
                                    {tab.count !== undefined && (
                                        <span className="tab-count">{tab.count}</span>
                                    )}
                                </button>
                            ))}
                        </div>

                        <div className="report-body">
                            {/* ─── OVERVIEW ─── */}
                            {activeTab === 'overview' && (
                                <div className="report-section">
                                    {/* Pipeline Status */}
                                    <div className="pipeline-flow">
                                        <div className="pipeline-step completed">
                                            <div className="step-dot">✓</div>
                                            <div className="step-info">
                                                <div className="step-name">Scan</div>
                                                <div className="step-detail">{vulns.length} issues found</div>
                                            </div>
                                        </div>
                                        <div className="pipeline-connector"></div>
                                        <div className="pipeline-step completed">
                                            <div className="step-dot">✓</div>
                                            <div className="step-info">
                                                <div className="step-name">Detect</div>
                                                <div className="step-detail">{eco?.language || '—'}</div>
                                            </div>
                                        </div>
                                        <div className="pipeline-connector"></div>
                                        <div className="pipeline-step completed">
                                            <div className="step-dot">✓</div>
                                            <div className="step-info">
                                                <div className="step-name">Fix</div>
                                                <div className="step-detail">{remediations.length} patches</div>
                                            </div>
                                        </div>
                                        <div className="pipeline-connector"></div>
                                        <div className={`pipeline-step ${verifiedCount === verifications.length ? 'completed' : 'warning'}`}>
                                            <div className="step-dot">{verifiedCount === verifications.length ? '✓' : '!'}</div>
                                            <div className="step-info">
                                                <div className="step-name">Verify</div>
                                                <div className="step-detail">{verifiedCount}/{verifications.length} passed</div>
                                            </div>
                                        </div>
                                    </div>

                                    {/* Stats Cards */}
                                    <div className="stats-grid">
                                        <div className="stat-card stat-danger">
                                            <div className="stat-icon">🚨</div>
                                            <div className="stat-value">{vulns.length}</div>
                                            <div className="stat-label">Issues Found</div>
                                        </div>
                                        <div className="stat-card stat-info">
                                            <div className="stat-icon">{eco?.language === 'python' ? '🐍' : eco?.language === 'javascript' ? '📜' : '⚙️'}</div>
                                            <div className="stat-value capitalize">{eco?.language || '—'}</div>
                                            <div className="stat-label">Language</div>
                                        </div>
                                        <div className="stat-card stat-primary">
                                            <div className="stat-icon">🛡️</div>
                                            <div className="stat-value">{remediations.length}</div>
                                            <div className="stat-label">Fixes Generated</div>
                                        </div>
                                        <div className="stat-card stat-success">
                                            <div className="stat-icon">✅</div>
                                            <div className="stat-value">{verifiedCount}/{verifications.length}</div>
                                            <div className="stat-label">Verified</div>
                                        </div>
                                    </div>

                                    {/* Libraries */}
                                    {Object.keys(libs).length > 0 && (
                                        <div className="report-card">
                                            <div className="card-title">📦 Detected Dependencies</div>
                                            <div className="lib-tags">
                                                {Object.entries(libs).map(([lang, packages]) =>
                                                    packages.map((pkg) => (
                                                        <span key={`${lang}-${pkg}`} className="lib-tag">
                                                            <span className="lib-lang">{lang}</span>
                                                            {pkg}
                                                        </span>
                                                    ))
                                                )}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            )}

                            {/* ─── SCANNER / FINDINGS ─── */}
                            {activeTab === 'scanner' && (
                                <div className="report-section">
                                    {vulns.length === 0 ? (
                                        <div className="report-empty-state small">
                                            <span className="report-empty-icon">🎉</span>
                                            <h4>All Clear</h4>
                                            <p>No vulnerabilities detected in your code.</p>
                                        </div>
                                    ) : (
                                        <div className="findings-list">
                                            {vulns.map((v, i) => (
                                                <div key={i} className="finding-card">
                                                    <div className="finding-top">
                                                        <span className="finding-severity">
                                                            {severityIcon(v.severity)} {v.severity}
                                                        </span>
                                                        <span className="finding-rule">{v.id}</span>
                                                    </div>
                                                    <div className="finding-location">
                                                        {getLangIcon(v.path)} <code>{v.path}{v.line > 0 ? `:${v.line}` : ''}</code>
                                                    </div>
                                                    <div className="finding-desc">{v.msg}</div>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            )}

                            {/* ─── ECOSYSTEM / ENVIRONMENT ─── */}
                            {activeTab === 'ecosystem' && (
                                <div className="report-section">
                                    {eco ? (
                                        <div className="env-card">
                                            <div className="env-title">
                                                {eco.language === 'python' ? '🐍' : eco.language === 'javascript' ? '📜' : '⚙️'}
                                                AI-Detected Environment
                                            </div>
                                            <div className="env-grid">
                                                <div className="env-item">
                                                    <div className="env-key">Language</div>
                                                    <div className="env-val capitalize">{eco.language}</div>
                                                </div>
                                                <div className="env-item">
                                                    <div className="env-key">Docker Image</div>
                                                    <div className="env-val"><code>{eco.docker_image}</code></div>
                                                </div>
                                                <div className="env-item full-width">
                                                    <div className="env-key">Install Command</div>
                                                    <div className="env-val"><code>{eco.dep_install_cmd || 'None'}</code></div>
                                                </div>
                                            </div>
                                        </div>
                                    ) : (
                                        <div className="report-empty-state small">
                                            <span className="report-empty-icon">❓</span>
                                            <h4>No Environment Data</h4>
                                            <p>Environment detection didn't produce results.</p>
                                        </div>
                                    )}
                                </div>
                            )}

                            {/* ─── REMEDIATION / CODE CHANGES ─── */}
                            {activeTab === 'remediation' && (
                                <div className="report-section">
                                    {remediations.length === 0 ? (
                                        <div className="report-empty-state small">
                                            <span className="report-empty-icon">🔧</span>
                                            <h4>No Fixes Generated</h4>
                                            <p>The AI agent didn't generate any code changes.</p>
                                        </div>
                                    ) : (
                                        <div className="changes-list">
                                            {remediations.map((fix, i) => {
                                                const isExpanded = expandedFix === i;
                                                const verification = verifications.find(v => v.path === fix.path);
                                                return (
                                                    <div key={i} className="change-card">
                                                        <div className="change-header" onClick={() => setExpandedFix(isExpanded ? null : i)}>
                                                            <div className="change-file">
                                                                {getLangIcon(fix.path)}
                                                                <span className="change-filename">{fix.path.split('/').pop()}</span>
                                                                <span className="change-filepath">{fix.path}</span>
                                                            </div>
                                                            <div className="change-badges">
                                                                {verification && (
                                                                    <span className={`change-status ${verification.verified ? 'pass' : 'fail'}`}>
                                                                        {verification.verified ? '✅ Verified' : '❌ Failed'}
                                                                    </span>
                                                                )}
                                                                <span className="change-expand">{isExpanded ? '▼' : '▶'}</span>
                                                            </div>
                                                        </div>
                                                        {isExpanded && (
                                                            <div className="change-body">
                                                                <div className="code-toggle">
                                                                    <button
                                                                        className={`toggle-btn ${codeView === 'before' ? 'active-before' : ''}`}
                                                                        onClick={() => setCodeView('before')}
                                                                    >
                                                                        ⚠️ Before <span className="toggle-sub">Vulnerable</span>
                                                                    </button>
                                                                    <button
                                                                        className={`toggle-btn ${codeView === 'after' ? 'active-after' : ''}`}
                                                                        onClick={() => setCodeView('after')}
                                                                    >
                                                                        🛡️ After <span className="toggle-sub">Fixed by AI</span>
                                                                    </button>
                                                                </div>
                                                                <div className={`code-container ${codeView === 'before' ? 'code-before' : 'code-after'}`}>
                                                                    <div className="code-header">
                                                                        <span>{codeView === 'before' ? '⚠️ Original Vulnerable Code' : '🛡️ AI-Fixed Secure Code'}</span>
                                                                        <span className="code-lang">{getFileExt(fix.path)}</span>
                                                                    </div>
                                                                    <pre className="code-block">
                                                                        {codeView === 'before'
                                                                            ? (fix.original_code || 'Original code not available for this scan.')
                                                                            : fix.fix_code}
                                                                    </pre>
                                                                </div>
                                                                {fix.test_code && (
                                                                    <div className="code-container code-test">
                                                                        <div className="code-header">
                                                                            <span>🧪 Verification Test</span>
                                                                            <span className="code-lang">auto-generated</span>
                                                                        </div>
                                                                        <pre className="code-block">{fix.test_code}</pre>
                                                                    </div>
                                                                )}
                                                            </div>
                                                        )}
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    )}
                                </div>
                            )}

                            {/* ─── VERIFICATION ─── */}
                            {activeTab === 'verification' && (
                                <div className="report-section">
                                    {verifications.length === 0 ? (
                                        <div className="report-empty-state small">
                                            <span className="report-empty-icon">🧪</span>
                                            <h4>No Verification Data</h4>
                                            <p>No fixes were tested.</p>
                                        </div>
                                    ) : (
                                        <>
                                            <div className="verify-summary">
                                                <div className={`verify-ring ${verifiedCount === verifications.length ? 'all-pass' : 'some-fail'}`}>
                                                    <span className="ring-number">{verifiedCount}</span>
                                                    <span className="ring-label">/ {verifications.length}</span>
                                                </div>
                                                <div className="verify-summary-text">
                                                    <h4>{verifiedCount === verifications.length ? 'All Tests Passed! 🎉' : 'Some Tests Failed'}</h4>
                                                    <p>{verifiedCount} of {verifications.length} fixes passed automated verification</p>
                                                </div>
                                            </div>
                                            <div className="verify-list">
                                                {verifications.map((v, i) => (
                                                    <div key={i} className={`verify-card ${v.verified ? 'pass' : 'fail'}`}>
                                                        <div className="verify-card-top">
                                                            <span className="verify-card-icon">{v.verified ? '✅' : '❌'}</span>
                                                            <div className="verify-card-path">
                                                                {getLangIcon(v.path)} {v.path.split('/').pop()}
                                                                <div className="verify-path-full">{v.path}</div>
                                                            </div>
                                                            <span className={`verify-badge ${v.verified ? 'pass' : 'fail'}`}>
                                                                {v.verified ? 'PASSED' : 'FAILED'}
                                                            </span>
                                                        </div>

                                                        {parsedTests(v.error || '').length > 0 && (
                                                            <div className="verify-tests-list">
                                                                {parsedTests(v.error || '').map((t, k) => (
                                                                    <div key={k} className={`verify-test-item ${t.status}`}>
                                                                        <span className="test-icon">{t.status === 'PASS' ? '✅' : '❌'}</span>
                                                                        <span className="test-name">{t.name}</span>
                                                                        {t.details && <span className="test-details">{t.details}</span>}
                                                                    </div>
                                                                ))}
                                                            </div>
                                                        )}

                                                        {v.error && (
                                                            <details className="verify-details">
                                                                <summary>View Raw Output</summary>
                                                                <pre className="verify-error-pre large-text">{v.error}</pre>
                                                            </details>
                                                        )}
                                                    </div>
                                                ))}
                                            </div>
                                        </>
                                    )}
                                </div>
                            )}
                        </div>
                    </>
                )}
            </div>
        </div>
    );
};
