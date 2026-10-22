/**
 * The component kit (plan UI-P): keyboard and ARIA done once, so every screen
 * built from it gets them. Each test is the behaviour a screen relies on.
 */
import { describe, expect, it, vi } from 'vitest';
import { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Button, Checkbox, Dialog, IconButton, Input, Progress, Stat, Tabs, Tooltip } from '.';

describe('Button', () => {
  it('is a plain button, and a loading one cannot be pressed again', async () => {
    const pressed = vi.fn();
    render(<Button loading onClick={pressed}>Save</Button>);
    const button = screen.getByRole('button', { name: 'Save' });
    expect(button).toHaveProperty('type', 'button');
    expect(button.getAttribute('aria-busy')).toBe('true');
    await userEvent.click(button);
    expect(pressed).not.toHaveBeenCalled();
  });
});

describe('IconButton', () => {
  it('is named by its label', () => {
    render(<IconButton label="Search runs" icon={<svg />} />);
    expect(screen.getByRole('button', { name: 'Search runs' })).toBeTruthy();
  });
});

describe('Tabs', () => {
  const items = [
    { id: 'work', label: 'Work', content: <p>work panel</p> },
    { id: 'changes', label: 'Changes', content: <p>changes panel</p> },
    { id: 'evidence', label: 'Evidence', content: <p>evidence panel</p> },
  ];

  it('has one tab stop and moves with the arrow keys, Home and End', async () => {
    render(<Tabs label="Run sections" items={items} />);
    const [work, changes, evidence] = screen.getAllByRole('tab');
    expect([work.tabIndex, changes.tabIndex, evidence.tabIndex]).toEqual([0, -1, -1]);
    work.focus();
    await userEvent.keyboard('{ArrowRight}');
    expect(document.activeElement).toBe(changes);
    expect(changes.getAttribute('aria-selected')).toBe('true');
    expect(screen.getByText('changes panel')).toBeTruthy();
    await userEvent.keyboard('{End}');
    expect(document.activeElement).toBe(evidence);
    await userEvent.keyboard('{ArrowRight}');
    expect(document.activeElement).toBe(work);
  });

  it('can be held by its caller, who keeps the address', async () => {
    const chosen: string[] = [];
    const Held = () => {
      const [tab, setTab] = useState('changes');
      return <Tabs label="Work area" items={items} selected={tab} onSelect={(id) => { chosen.push(id); setTab(id); }} />;
    };
    render(<Held />);
    expect(screen.getByText('changes panel')).toBeTruthy();
    const before = window.location.search;

    await userEvent.click(screen.getByRole('tab', { name: 'Evidence' }));

    expect(chosen).toEqual(['evidence']);
    expect(screen.getByText('evidence panel')).toBeTruthy();
    expect(window.location.search).toBe(before);
  });

  it('keeps the chosen tab in the address and opens it from there', async () => {
    window.history.replaceState(null, '', '/runs/x?tab=evidence');
    render(<Tabs label="Run sections" items={items} param="tab" />);
    expect(screen.getByRole('tab', { name: 'Evidence' }).getAttribute('aria-selected')).toBe('true');
    await userEvent.click(screen.getByRole('tab', { name: 'Work' }));
    expect(new URLSearchParams(window.location.search).get('tab')).toBe('work');
  });

  it('labels each panel by its tab', () => {
    render(<Tabs label="Run sections" items={items} />);
    const panel = screen.getByRole('tabpanel');
    expect(panel.getAttribute('aria-labelledby')).toBe(screen.getAllByRole('tab')[0].id);
  });
});

function DialogHarness({ onClose }: { onClose?: () => void }) {
  const [open, setOpen] = useState(false);
  const close = () => { setOpen(false); onClose?.(); };
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>Open</button>
      <Dialog open={open} onClose={close} title="Cancel this run?" description="It stops at the next boundary."
        footer={<><button type="button">Keep it</button><button type="button">Cancel it</button></>} />
    </>
  );
}

describe('Dialog', () => {
  it('is a labelled modal that keeps focus inside, closes on Escape and gives focus back', async () => {
    const closed = vi.fn();
    render(<DialogHarness onClose={closed} />);
    const opener = screen.getByRole('button', { name: 'Open' });
    await userEvent.click(opener);
    const dialog = screen.getByRole('dialog', { name: 'Cancel this run?' });
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    expect(dialog.getAttribute('aria-describedby')).toBeTruthy();
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Keep it' }));
    await userEvent.tab();
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Cancel it' }));
    await userEvent.tab();
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Keep it' }));
    await userEvent.keyboard('{Escape}');
    expect(closed).toHaveBeenCalled();
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(opener);
  });
});

describe('fields', () => {
  it('read their hint and error with the control, and mark it invalid', () => {
    render(<Input label="Model" hint="The served name" error="Not served at that address" />);
    const input = screen.getByLabelText('Model');
    const described = (input.getAttribute('aria-describedby') || '').split(' ').map((id) => document.getElementById(id)?.textContent);
    expect(described).toEqual(['The served name', 'Not served at that address']);
    expect(input.getAttribute('aria-invalid')).toBe('true');
  });

  it('a checkbox is labelled by the words beside it', async () => {
    render(<Checkbox label="Approve each gate myself" hint="The run pauses" />);
    const box = screen.getByRole('checkbox', { name: 'Approve each gate myself' });
    await userEvent.click(screen.getByText('Approve each gate myself'));
    expect((box as HTMLInputElement).checked).toBe(true);
  });
});

describe('display', () => {
  it('a progress bar says how far, and an indeterminate one does not claim to', () => {
    render(<><Progress label="Sprint" value={2} max={3} /><Progress label="Waiting" /></>);
    const [known, unknown] = screen.getAllByRole('progressbar');
    expect(known.getAttribute('aria-valuenow')).toBe('2');
    expect(known.getAttribute('aria-valuemax')).toBe('3');
    expect(unknown.hasAttribute('aria-valuenow')).toBe(false);
  });

  it('a tooltip shows on keyboard focus and describes its trigger', async () => {
    render(<Tooltip text="Runs waiting for you"><button type="button">Needs you</button></Tooltip>);
    const trigger = screen.getByRole('button', { name: 'Needs you' });
    expect(screen.getByRole('tooltip', { hidden: true }).hidden).toBe(true);
    await userEvent.tab();
    expect(document.activeElement).toBe(trigger);
    const tip = screen.getByRole('tooltip');
    expect(tip.hidden).toBe(false);
    expect(trigger.getAttribute('aria-describedby')).toBe(tip.id);
  });

  it('a number carries where it came from', () => {
    render(<dl><Stat label="Criteria proven" value="9 of 12" source="the locked suite" /></dl>);
    expect(screen.getByText('the locked suite')).toBeTruthy();
  });
});
