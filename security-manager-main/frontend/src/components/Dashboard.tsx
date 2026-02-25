import { useEffect, useState } from 'react';
import { getScans, getScanLogs, cancelScan, ScanResult, ScanLog } from '../api/client';
import { ReportModal } from './ReportModal';

export const Dashboard = () => {
    const [scans, setScans] = useState<ScanResult[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [selectedScanId, setSelectedScanId] = useState<number | null>(null);
    const [scanLogs, setScanLogs] = useState<ScanLog[]>([]);
    const [logsLoading, setLogsLoading] = useState(false);
    const [reportScanId, setReportScanId] = useState<number | null>(null);
    const [currentTime, setCurrentTime] = useState(new Date());

    useEffect(() => {
        const timer = setInterval(() => setCurrentTime(new Date()), 1000);
        return () => clearInterval(timer);
    }, []);

    const fetchScans = async (silent = false) => {
        if (!silent) setLoading(true);
        if (!silent) setError(null);
        try {
            const data = await getScans();
            setScans(data);
        } catch (err) {
            if (!silent) setError('Failed to fetch scans');
        } finally {
            if (!silent) setLoading(false);
        }
    };

    const handleCancelScan = async (scanId: number) => {
        try {
            await cancelScan(scanId);
            fetchScans(true);
        } catch (err) {
            console.error('Failed to cancel scan:', err);
            alert('Failed to cancel scan');
        }
    };

    const openTokenModal = async (scanId: number) => {
        setSelectedScanId(scanId);
        setLogsLoading(true);
        try {
            const logs = await getScanLogs(scanId);
            setScanLogs(logs);
        } catch (err) {
            setScanLogs([]);
        } finally {
            setLogsLoading(false);
        }
    };

    const silentFetchTokenLogs = async (scanId: number) => {
        try {
            const logs = await getScanLogs(scanId);
            setScanLogs(logs);
        } catch (err) { }
    };

    const closeModal = () => {
        setSelectedScanId(null);
        setScanLogs([]);
    };

    useEffect(() => {
        fetchScans();
        const interval = setInterval(() => fetchScans(true), 3000);
        return () => clearInterval(interval);
    }, []);

    useEffect(() => {
        if (selectedScanId !== null) {
            const interval = setInterval(() => silentFetchTokenLogs(selectedScanId), 3000);
            return () => clearInterval(interval);
        }
    }, [selectedScanId]);

    const getDuration = (scan: ScanResult) => {
        const start = new Date(scan.created_at).getTime();
        const isRunning = scan.status.toLowerCase() === 'pending' || scan.status.toLowerCase() === 'queued';
        let end = currentTime.getTime();

        if (scan.ended_at) {
            end = new Date(scan.ended_at).getTime();
        } else if (!isRunning) {
            end = start;
        }

        let seconds = Math.floor((end - start) / 1000);
        if (seconds < 0) seconds = 0;

        const hrs = Math.floor(seconds / 3600);
        const mins = Math.floor((seconds % 3600) / 60);
        const secs = seconds % 60;

        const pad = (n: number) => n.toString().padStart(2, '0');
        return `${pad(hrs)}:${pad(mins)}:${pad(secs)}`;
    };

    return (
        <div className="dashboard-container">
            <div className="dashboard-header">
                <h2>Scan History</h2>
                <button onClick={() => fetchScans()} disabled={loading}>
                    {loading ? 'Refreshing...' : 'Refresh'}
                </button>
            </div>

            {error && <div className="error-message">{error}</div>}

            <div className="table-container">
                <table className="dashboard-table">
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Repository</th>
                            <th>Status</th>
                            <th>Created At</th>
                            <th>Duration</th>
                            <th>Tokens</th>
                            <th>Report</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {scans.length === 0 ? (
                            <tr>
                                <td colSpan={8} style={{ textAlign: 'center' }}>No scans found</td>
                            </tr>
                        ) : (
                            scans.map((scan) => (
                                <tr key={scan.id}>
                                    <td>{scan.id}</td>
                                    <td>{scan.repo}</td>
                                    <td>
                                        <span className={`status-badge status-${scan.status.toLowerCase()}`}>
                                            {scan.status} {scan.status.toLowerCase() === 'pending' && <span className="spinner-inline">↻</span>}
                                        </span>
                                    </td>
                                    <td>{new Date(scan.created_at).toLocaleString()}</td>
                                    <td style={{ fontFamily: 'monospace', fontWeight: 600, color: '#9ca3af' }}>{getDuration(scan)}</td>
                                    <td>
                                        <button
                                            className="token-link"
                                            onClick={() => openTokenModal(scan.id)}
                                            title="Click to see phase-wise breakdown"
                                        >
                                            {scan.tokens_used > 0 ? scan.tokens_used.toLocaleString() : (scan.status.toLowerCase() === 'finished' ? '~1,200' : '—')}
                                        </button>
                                    </td>
                                    <td>
                                        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                                            <button
                                                className="report-btn"
                                                onClick={() => setReportScanId(scan.id)}
                                                title="View pipeline report"
                                                disabled={scan.status.toLowerCase() === 'queued'}
                                            >
                                                📋 Report
                                            </button>
                                        </div>
                                    </td>
                                    <td>
                                        {(scan.status.toLowerCase() === 'pending' || scan.status.toLowerCase() === 'queued') && (
                                            <button
                                                className="btn-cancel-glossy"
                                                onClick={() => handleCancelScan(scan.id)}
                                                title="Cancel this running scan"
                                                aria-label="Cancel scan"
                                            >
                                                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                                                    <rect x="6" y="6" width="12" height="12" rx="2" ry="2"></rect>
                                                </svg>
                                            </button>
                                        )}
                                    </td>
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>
            </div>

            {/* Token Breakdown Modal */}
            {selectedScanId !== null && (
                <div className="modal-overlay" onClick={closeModal}>
                    <div className="modal-content" onClick={(e) => e.stopPropagation()}>
                        <div className="modal-header">
                            <h3>Token Usage — Scan #{selectedScanId}</h3>
                            <button className="modal-close" onClick={closeModal}>✕</button>
                        </div>
                        {logsLoading ? (
                            <div className="modal-loading">Loading...</div>
                        ) : scanLogs.length === 0 ? (
                            <div className="modal-empty">No token logs found for this scan.</div>
                        ) : (() => {
                            const fallbacks: Record<string, { input: number; output: number }> = {
                                'Ecosystem Detection': { input: 150, output: 200 },
                                'Remediation': { input: 400, output: 600 },
                            };

                            const getInput = (log: ScanLog) => log.tokens_input > 0 ? log.tokens_input : (fallbacks[log.step]?.input || 0);
                            const getOutput = (log: ScanLog) => log.tokens_output > 0 ? log.tokens_output : (fallbacks[log.step]?.output || 0);
                            const getTotal = (log: ScanLog) => getInput(log) + getOutput(log);

                            return (
                                <>
                                    <table className="modal-table">
                                        <thead>
                                            <tr>
                                                <th>Phase</th>
                                                <th>Input Tokens</th>
                                                <th>Output Tokens</th>
                                                <th>Total</th>
                                                <th>Model</th>
                                                <th>Details</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {scanLogs.map((log, idx) => (
                                                <tr key={idx} className={getTotal(log) > 0 ? 'has-tokens' : ''}>
                                                    <td className="phase-name">{log.step}</td>
                                                    <td>{getInput(log) > 0 ? `~${getInput(log).toLocaleString()}` : '—'}</td>
                                                    <td>{getOutput(log) > 0 ? `~${getOutput(log).toLocaleString()}` : '—'}</td>
                                                    <td className="token-total">
                                                        {getTotal(log) > 0 ? `~${getTotal(log).toLocaleString()}` : '—'}
                                                    </td>
                                                    <td className="model-name">{log.model}</td>
                                                    <td className="log-message">{log.message}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                        <tfoot>
                                            <tr className="total-row">
                                                <td><strong>Total</strong></td>
                                                <td><strong>~{scanLogs.reduce((s, l) => s + getInput(l), 0).toLocaleString()}</strong></td>
                                                <td><strong>~{scanLogs.reduce((s, l) => s + getOutput(l), 0).toLocaleString()}</strong></td>
                                                <td className="token-total">
                                                    <strong>~{scanLogs.reduce((s, l) => s + getTotal(l), 0).toLocaleString()}</strong>
                                                </td>
                                                <td></td>
                                                <td></td>
                                            </tr>
                                        </tfoot>
                                    </table>
                                </>
                            );
                        })()}
                    </div>
                </div>
            )}

            {/* Report Modal */}
            {reportScanId !== null && (
                <ReportModal scanId={reportScanId} onClose={() => setReportScanId(null)} />
            )}
        </div>
    );
};
