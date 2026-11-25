import { describe, expect, it, vi } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import { Editor } from './Editor';

// The editor's chunk does not arrive: a dropped connection, a stale deploy, a blocked script.
vi.mock('./monaco', () => {
  throw new Error('The editor chunk did not load');
});

const settled = () => act(async () => { await new Promise((resolve) => setTimeout(resolve, 20)); });

describe('the workspace editor when it cannot load (plan UX.6)', () => {
  it("still shows the file's text, highlighted", async () => {
    render(<Editor path="src/app.py" text={"def greet():\n    return 'hi'\n"} />);
    await settled();

    expect(screen.getByLabelText('The text of src/app.py').textContent).toContain("return 'hi'");
    expect(screen.getByText('def').className).toContain('text-primary');
  });

  it('still shows a change, the text then beside the text now', async () => {
    render(<Editor path="src/app.py" text={"print('now')\n"} diff={{ base: "print('then')\n", since: 'sprint 1' }} />);
    await settled();

    expect(screen.getByLabelText('src/app.py at sprint 1').textContent).toContain("print('then')");
    expect(screen.getByText('Now')).toBeTruthy();
    expect(screen.getAllByLabelText('The text of src/app.py').map((code) => code.textContent).join()).toContain("print('now')");
  });
});
