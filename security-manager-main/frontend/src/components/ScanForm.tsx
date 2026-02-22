import React, { useState, useEffect } from 'react';
import { triggerScan, getConfig, setConfig } from '../api/client';
import { isValidGithubUrl } from '../utils/validation';

export const ScanForm: React.FC = () => {
    const [repoUrl, setRepoUrl] = useState('');
    const [targetUrl, setTargetUrl] = useState('');
    const [githubToken, setGithubToken] = useState('');
    const [webhookSecret, setWebhookSecret] = useState('');
    const [webhookSaved, setWebhookSaved] = useState(false);
    const [showSettings, setShowSettings] = useState(false);
    const [showSuccess, setShowSuccess] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);

    // Load existing config on mount
    useEffect(() => {
        getConfig().then((configs) => {
            const secret = configs.find((c) => c.key === 'GITHUB_WEBHOOK_SECRET');
            if (secret) setWebhookSecret(secret.value);
        }).catch(() => { });
    }, []);

    const saveWebhookSecret = async () => {
        if (!webhookSecret) return;
        try {
            await setConfig('GITHUB_WEBHOOK_SECRET', webhookSecret, true);
            setWebhookSaved(true);
            setTimeout(() => setWebhookSaved(false), 2000);
        } catch {
            setError('Failed to save webhook secret');
        }
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        if (!isValidGithubUrl(repoUrl)) {
            setError('Invalid GitHub URL. Please use format: https://github.com/username/repo');
            return;
        }

        if (targetUrl && !targetUrl.startsWith('http')) {
            setError('Application URL must start with http:// or https://');
            return;
        }

        setLoading(true);
        setError(null);
        setShowSuccess(false);

        try {
            await triggerScan(repoUrl, targetUrl || undefined, githubToken || undefined);
            setShowSuccess(true);
            setRepoUrl('');
            setTargetUrl('');
            setTimeout(() => setShowSuccess(false), 5000);
        } catch (err: any) {
            setError(err.message || 'Failed to trigger scan');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="card">
            <h2>Start New Scan</h2>
            <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <div>
                    <label className="input-label">Repository URL <span className="required">*</span></label>
                    <input
                        type="text"
                        placeholder="https://github.com/owner/repo"
                        value={repoUrl}
                        onChange={(e) => setRepoUrl(e.target.value)}
                        required
                    />
                </div>
                <div>
                    <label className="input-label">
                        Application URL
                        <span className="optional-badge">Optional</span>
                    </label>
                    <input
                        type="text"
                        placeholder="https://myapp.example.com"
                        value={targetUrl}
                        onChange={(e) => setTargetUrl(e.target.value)}
                    />
                    <p className="input-hint">
                        Live app URL for DAST scanning (ZAP). Leave empty to run code-only scans.
                    </p>
                </div>

                {/* Collapsible GitHub Settings */}
                <div className="settings-section">
                    <button
                        type="button"
                        className="settings-toggle"
                        onClick={() => setShowSettings(!showSettings)}
                    >
                        <span className="settings-icon">{showSettings ? '▾' : '▸'}</span>
                        GitHub Settings
                    </button>
                    {showSettings && (
                        <div className="settings-content">
                            <div>
                                <label className="input-label">
                                    GitHub Token
                                    <span className="optional-badge">For Private Repos</span>
                                </label>
                                <input
                                    type="password"
                                    placeholder="ghp_xxxxxxxxxxxxxxxxxxxx"
                                    value={githubToken}
                                    onChange={(e) => setGithubToken(e.target.value)}
                                />
                                <p className="input-hint">
                                    Personal Access Token with <code>repo</code> scope. Required for private repositories and commit status updates.
                                </p>
                            </div>
                            <div style={{ marginTop: '0.75rem' }}>
                                <label className="input-label">
                                    Webhook Secret
                                    <span className="optional-badge">For PR Scanning</span>
                                </label>
                                <div className="webhook-row">
                                    <input
                                        type="password"
                                        placeholder="your-webhook-secret"
                                        value={webhookSecret}
                                        onChange={(e) => setWebhookSecret(e.target.value)}
                                        style={{ flex: 1 }}
                                    />
                                    <button
                                        type="button"
                                        onClick={saveWebhookSecret}
                                        style={{ whiteSpace: 'nowrap' }}
                                    >
                                        {webhookSaved ? '✓ Saved' : 'Save'}
                                    </button>
                                </div>
                                <p className="input-hint">
                                    Must match the secret configured in your GitHub webhook settings.
                                </p>
                            </div>
                        </div>
                    )}
                </div>

                <button type="submit" disabled={loading}>
                    {loading ? 'Scanning...' : 'Trigger Scan'}
                </button>
            </form>

            {error && <p style={{ color: '#f87171', marginTop: '1rem' }}>{error}</p>}

            {showSuccess && (
                <div style={{ marginTop: '1rem', textAlign: 'left', background: 'rgba(16, 185, 129, 0.1)', color: '#34d399', padding: '1rem', borderRadius: '8px', border: '1px solid rgba(16, 185, 129, 0.2)' }}>
                    <h3 style={{ margin: '0 0 0.25rem 0', fontSize: '1rem' }}>✓ Scan Successfully Queued!</h3>
                    <p style={{ margin: 0, fontSize: '0.85rem', color: '#a0aec0' }}>The scan is now running in the background. Check the dashboard below for real-time updates.</p>
                </div>
            )}
        </div>
    );
};

