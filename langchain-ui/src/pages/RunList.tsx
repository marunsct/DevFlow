import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { listRuns } from '../api';
import type { RunSummary } from '../types';
import { Clock, Activity, AlertCircle, CheckCircle2, XCircle, ListFilter } from 'lucide-react';

export const RunList: React.FC = () => {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchRuns = async () => {
      try {
        const response = await listRuns();
        // Sort runs by created_at descending (newest first)
        const sortedRuns = response.runs.sort(
          (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        );
        setRuns(sortedRuns);
      } catch (err: any) {
        console.error(err);
        setError("Failed to load past runs.");
      } finally {
        setLoading(false);
      }
    };
    fetchRuns();
  }, []);

  const getStatusConfig = (status: string) => {
    const config = {
      created: { color: 'bg-slate-100 text-slate-700', icon: Clock },
      running: { color: 'bg-blue-100 text-blue-700', icon: Activity },
      waiting_for_review: { color: 'bg-warning/20 text-warning-800', icon: AlertCircle },
      waiting_for_approval: { color: 'bg-danger/20 text-danger-800', icon: AlertCircle },
      completed: { color: 'bg-success/20 text-success-800', icon: CheckCircle2 },
      failed: { color: 'bg-danger/20 text-danger-800', icon: XCircle },
      cancelled: { color: 'bg-slate-100 text-slate-700', icon: XCircle },
      paused: { color: 'bg-warning/20 text-warning-800', icon: Clock }
    };
    return config[status as keyof typeof config] || config.created;
  };

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Past Runs</h1>
          <p className="text-sm text-slate-500">View and manage all your workflow runs</p>
        </div>
        <Link 
          to="/"
          className="bg-primary hover:bg-primary/90 text-primary-foreground font-medium rounded-lg px-4 py-2 transition-colors"
        >
          New Run
        </Link>
      </div>

      {loading ? (
        <div className="flex items-center justify-center min-h-[40vh]">
          <div className="h-10 w-10 border-4 border-primary border-t-transparent rounded-full animate-spin"></div>
        </div>
      ) : error ? (
        <div className="p-8 bg-danger/10 border border-danger/30 rounded-lg text-danger text-center">
          <AlertCircle className="h-10 w-10 mx-auto mb-4" />
          <p>{error}</p>
        </div>
      ) : runs.length === 0 ? (
        <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-12 text-center">
          <ListFilter className="h-12 w-12 text-slate-300 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-slate-800 mb-1">No runs found</h3>
          <p className="text-slate-500 mb-6">You haven't started any workflow runs yet.</p>
          <Link 
            to="/"
            className="inline-flex items-center justify-center bg-primary hover:bg-primary/90 text-primary-foreground font-medium rounded-lg px-6 py-2 transition-colors"
          >
            Start Your First Run
          </Link>
        </div>
      ) : (
        <div className="bg-white rounded-lg shadow-sm border border-slate-200 overflow-hidden">
          <table className="min-w-full divide-y divide-slate-200">
            <thead className="bg-slate-50">
              <tr>
                <th scope="col" className="px-6 py-4 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">
                  Run ID
                </th>
                <th scope="col" className="px-6 py-4 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">
                  Status
                </th>
                <th scope="col" className="px-6 py-4 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">
                  Current Stage
                </th>
                <th scope="col" className="px-6 py-4 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">
                  Started
                </th>
                <th scope="col" className="px-6 py-4 text-right text-xs font-semibold text-slate-500 uppercase tracking-wider">
                  Action
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-slate-200">
              {runs.map((run) => {
                const config = getStatusConfig(run.status);
                const StatusIcon = config.icon;
                return (
                  <tr key={run.run_id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="text-sm font-mono text-slate-900">{run.run_id}</div>
                      {run.document_name && (
                        <div className="text-xs text-slate-500 truncate max-w-[200px]" title={run.document_name}>
                          {run.document_name}
                        </div>
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${config.color}`}>
                        <StatusIcon className="h-3.5 w-3.5" />
                        <span className="uppercase tracking-wider">{run.status.replace(/_/g, ' ')}</span>
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-600">
                      {run.current_stage || 'Not started'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-500">
                      {new Date(run.created_at).toLocaleString()}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                      <Link 
                        to={`/runs/${run.run_id}`}
                        className="text-primary hover:text-primary/80"
                      >
                        View Dashboard &rarr;
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
