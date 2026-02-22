import { Dashboard } from './components/Dashboard';
import { ScanForm } from './components/ScanForm';
import './App.css';

function App() {
    return (
        <div className="container">
            <h1>Security Guardian Dashboard</h1>
            <p>Shift-Left Security Automation with Agentic AI</p>

            <div className="dashboard-grid">
                <ScanForm />
                <Dashboard />
            </div>
        </div>
    )
}

export default App
