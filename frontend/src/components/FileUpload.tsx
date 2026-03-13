import { useCallback } from 'react';
import { useDropzone } from 'react-dropzone';

interface FileUploadProps {
  onFileDrop: (file: File) => void;
  isLoading: boolean;
  error?: string;
}

function FileUpload({ onFileDrop, isLoading, error }: FileUploadProps) {
  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      if (acceptedFiles.length > 0) {
        onFileDrop(acceptedFiles[0]);
      }
    },
    [onFileDrop]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
      'message/rfc822': ['.eml'],
      'application/vnd.ms-outlook': ['.msg'],
    },
    maxFiles: 1,
    disabled: isLoading,
  });

  return (
    <div className="space-y-3">
      <div
        {...getRootProps()}
        className={`
          border-2 border-dashed rounded-xl p-12 text-center cursor-pointer
          transition-all duration-300
          ${isDragActive
            ? 'border-pp-accent bg-pp-accent/10 scale-[1.01]'
            : 'border-pp-border bg-pp-surface hover:border-pp-accent/50 hover:bg-pp-surface-light'
          }
          ${isLoading ? 'opacity-50 cursor-wait' : ''}
        `}
      >
        <input {...getInputProps()} />

        {isLoading ? (
          <div className="flex flex-col items-center gap-3">
            <div className="w-8 h-8 border-2 border-pp-accent border-t-transparent rounded-full animate-spin" />
            <p className="text-sm text-pp-text-muted">Przetwarzanie pliku...</p>
          </div>
        ) : isDragActive ? (
          <div className="flex flex-col items-center gap-3">
            <svg className="w-12 h-12 text-pp-accent" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M9 19l3-3m0 0l3 3m-3-3v12" />
            </svg>
            <p className="text-sm text-pp-accent font-medium">Upuść plik tutaj</p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3">
            <svg className="w-12 h-12 text-pp-text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
            <div>
              <p className="text-sm text-pp-text font-medium">
                Przeciągnij plik lub <span className="text-pp-accent underline">wybierz z dysku</span>
              </p>
              <p className="text-xs text-pp-text-muted mt-1">DOCX, XLSX, EML, MSG — maks. 50 MB</p>
            </div>
            <div className="flex items-center gap-1.5 mt-2 px-3 py-1.5 bg-pp-green/20 rounded-full">
              <div className="w-1.5 h-1.5 bg-pp-green-text rounded-full" />
              <span className="text-xs text-pp-green-text">Pliki przetwarzane lokalnie</span>
            </div>
          </div>
        )}
      </div>

      {error && (
        <div className="flex items-center gap-2 px-4 py-2.5 bg-red-900/20 border border-red-800 rounded-xl">
          <span className="text-sm text-red-400">✗ {error}</span>
        </div>
      )}
    </div>
  );
}

export default FileUpload;
