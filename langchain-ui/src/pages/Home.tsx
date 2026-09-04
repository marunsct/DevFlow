import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { UploadCloud, File, PlayCircle } from 'lucide-react';
import { createRun, startRun } from '../api';

export const Home: React.FC = () => {
  const [files, setFiles] = useState<File[]>([]);
  const [artifactDirectory, setArtifactDirectory] = useState<string>('');
  const [allowSubdirectories, setAllowSubdirectories] = useState<boolean>(true);
  const [reviewIntake, setReviewIntake] = useState<boolean>(true);
  const [reviewTechSpec, setReviewTechSpec] = useState<boolean>(true);
  const [reviewSprint, setReviewSprint] = useState<boolean>(true);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setFiles(Array.from(e.target.files));
      setError(null);
    }
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      setFiles(Array.from(e.dataTransfer.files));
      setError(null);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (files.length === 0) {
      setError("Please select at least one file to upload.");
      return;
    }

    setIsUploading(true);
    setError(null);

    try {
      // 1. Create the run by uploading the files
      const runData = await createRun(files);
      
      // 2. Start the run
      await startRun(runData.run_id, {
        reviewer: "Product Manager", // Can be made dynamic later
        artifact_directory: artifactDirectory || undefined,
        allow_subdirectories: allowSubdirectories,
        review_policy: {
          product_intake: reviewIntake,
          technical_specification: reviewTechSpec,
          sprint: reviewSprint
        }
      });
      
      // 3. Navigate to the dashboard
      navigate(`/runs/${runData.run_id}`);
    } catch (err: any) {
      console.error(err);
      setError(err.response?.data?.detail || err.message || "An error occurred during upload.");
      setIsUploading(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto mt-10">
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
        <div className="p-8 text-center border-b border-slate-100 bg-slate-50">
          <h1 className="text-2xl font-bold text-slate-800 mb-2">Start New Product Workflow</h1>
          <p className="text-slate-500">Upload your product intake document to begin the automated development process.</p>
        </div>

        <div className="p-8">
          <form onSubmit={handleSubmit}>
            <div 
              className={`border-2 border-dashed rounded-lg p-12 text-center transition-colors cursor-pointer
                ${files.length > 0 ? 'border-primary/50 bg-primary/5' : 'border-slate-300 hover:border-primary/50 hover:bg-slate-50'}
              `}
              onDragOver={handleDragOver}
              onDrop={handleDrop}
              onClick={() => document.getElementById('file-upload')?.click()}
            >
              <input
                id="file-upload"
                type="file"
                multiple
                className="hidden"
                accept=".md,.txt,.pdf,.docx"
                onChange={handleFileChange}
              />
              
              {files.length === 0 ? (
                <div className="flex flex-col items-center">
                  <div className="h-16 w-16 bg-slate-100 rounded-full flex items-center justify-center mb-4 text-slate-400 group-hover:text-primary">
                    <UploadCloud className="h-8 w-8" />
                  </div>
                  <h3 className="text-lg font-medium text-slate-700 mb-1">Click to upload or drag and drop</h3>
                  <p className="text-sm text-slate-500">Markdown, PDF, TXT or DOCX (max 10MB)</p>
                </div>
              ) : (
                <div className="flex flex-col items-center">
                  <div className="h-16 w-16 bg-success/10 rounded-full flex items-center justify-center mb-4 text-success">
                    <File className="h-8 w-8" />
                  </div>
                  <h3 className="text-lg font-medium text-slate-800 mb-1">
                    {files.length} file{files.length > 1 ? 's' : ''} selected
                  </h3>
                  <ul className="text-sm text-slate-500 max-h-32 overflow-y-auto mb-2 w-full max-w-sm text-left">
                    {files.map((f, i) => (
                      <li key={i} className="truncate">
                        - {f.name} ({(f.size / 1024 / 1024).toFixed(2)} MB)
                      </li>
                    ))}
                  </ul>
                  <button 
                    type="button" 
                    className="mt-2 text-sm text-danger hover:underline"
                    onClick={(e) => { e.stopPropagation(); setFiles([]); }}
                  >
                    Remove files
                  </button>
                </div>
              )}
            </div>

            <div className="mt-6 space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Artifact Directory (Optional)
                </label>
                <input
                  type="text"
                  value={artifactDirectory}
                  onChange={(e) => setArtifactDirectory(e.target.value)}
                  placeholder="e.g., /home/user/my_project"
                  className="w-full px-4 py-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
                />
              </div>
              <div className="flex items-center">
                <input
                  id="allowSubdirectories"
                  type="checkbox"
                  checked={allowSubdirectories}
                  onChange={(e) => setAllowSubdirectories(e.target.checked)}
                  className="h-4 w-4 text-primary focus:ring-primary border-slate-300 rounded"
                />
                <label htmlFor="allowSubdirectories" className="ml-2 block text-sm text-slate-700">
                  Provide access to directory and its subdirectories
                </label>
              </div>

              <div className="pt-4 border-t border-slate-200">
                <label className="block text-sm font-medium text-slate-700 mb-2">
                  Enable Optional Review Gates
                </label>
                <div className="space-y-2">
                  <div className="flex items-center">
                    <input
                      id="reviewIntake"
                      type="checkbox"
                      checked={reviewIntake}
                      onChange={(e) => setReviewIntake(e.target.checked)}
                      className="h-4 w-4 text-primary focus:ring-primary border-slate-300 rounded"
                    />
                    <label htmlFor="reviewIntake" className="ml-2 block text-sm text-slate-700">
                      Product Intake Review
                    </label>
                  </div>
                  <div className="flex items-center">
                    <input
                      id="reviewTechSpec"
                      type="checkbox"
                      checked={reviewTechSpec}
                      onChange={(e) => setReviewTechSpec(e.target.checked)}
                      className="h-4 w-4 text-primary focus:ring-primary border-slate-300 rounded"
                    />
                    <label htmlFor="reviewTechSpec" className="ml-2 block text-sm text-slate-700">
                      Technical Specification Review
                    </label>
                  </div>
                  <div className="flex items-center">
                    <input
                      id="reviewSprint"
                      type="checkbox"
                      checked={reviewSprint}
                      onChange={(e) => setReviewSprint(e.target.checked)}
                      className="h-4 w-4 text-primary focus:ring-primary border-slate-300 rounded"
                    />
                    <label htmlFor="reviewSprint" className="ml-2 block text-sm text-slate-700">
                      End of Sprint Review
                    </label>
                  </div>
                </div>
              </div>
            </div>

            {error && (
              <div className="mt-6 p-4 bg-danger/10 border border-danger/30 rounded-md text-danger text-sm">
                {error}
              </div>
            )}

            <div className="mt-8 flex justify-end">
              <button
                type="submit"
                disabled={files.length === 0 || isUploading}
                className={`
                  flex items-center gap-2 px-6 py-3 rounded-md font-medium text-white transition-all
                  ${files.length === 0 || isUploading ? 'bg-slate-400 cursor-not-allowed' : 'bg-primary hover:bg-primary/90 shadow-md hover:shadow-lg'}
                `}
              >
                {isUploading ? (
                  <>
                    <div className="h-5 w-5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                    Starting Workflow...
                  </>
                ) : (
                  <>
                    <PlayCircle className="h-5 w-5" />
                    Start Run
                  </>
                )}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
};
