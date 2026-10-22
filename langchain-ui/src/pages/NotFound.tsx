import React from 'react';
import { Link } from 'react-router-dom';

/** An address this interface has no page for. */
export const NotFound: React.FC = () => (
  <div className="max-w-xl mt-16 space-y-3">
    <h1 className="text-2xl font-bold text-text-primary">That page does not exist</h1>
    <p className="text-text-secondary text-sm">
      The address may be old, or from a run that was deleted. Nothing was changed.
    </p>
    <p className="text-sm">
      <Link to="/runs" className="text-primary underline">See your runs</Link>
      <span className="text-text-muted"> or </span>
      <Link to="/" className="text-primary underline">start a build</Link>.
    </p>
  </div>
);
