export interface Task {
  id: string;
  title: string;
  description: string;
  completed: boolean;
}

export type FilterType = 'all' | 'active' | 'completed';

export interface TaskFormData {
  title: string;
  description: string;
}
