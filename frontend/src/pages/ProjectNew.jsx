import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { createProject, getCategories } from '../api';
import { useApi } from '../hooks/useApi';
import Card from '../components/Card';

export default function ProjectNew() {
  const navigate = useNavigate();
  const { data: categoriesData } = useApi(getCategories);
  const categories = categoriesData?.results || categoriesData || [];

  const [form, setForm] = useState({
    title: '', description: '', instructables_url: '', difficulty: 2,
    category_id: '', bonus_amount: '0', materials_budget: '0', due_date: '',
  });
  const [error, setError] = useState('');

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    try {
      const data = {
        ...form,
        difficulty: parseInt(form.difficulty),
        category_id: form.category_id || null,
        due_date: form.due_date || null,
        instructables_url: form.instructables_url || null,
      };
      const project = await createProject(data);
      navigate(`/projects/${project.id}`);
    } catch (err) {
      setError(err.message);
    }
  };

  const inputClass = 'w-full bg-forge-bg border border-forge-border rounded-lg px-3 py-2 text-forge-text text-sm focus:outline-none focus:border-amber-primary';

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <button onClick={() => navigate('/projects')} className="flex items-center gap-1 text-sm text-forge-text-dim hover:text-forge-text">
        <ArrowLeft size={16} /> Back
      </button>
      <h1 className="font-heading text-2xl font-bold">New Project</h1>

      <form onSubmit={handleSubmit}>
        <Card className="space-y-4">
          {error && <div className="text-red-400 text-sm bg-red-400/10 px-3 py-2 rounded-lg">{error}</div>}

          <div>
            <label className="block text-sm text-forge-text-dim mb-1">Title</label>
            <input value={form.title} onChange={set('title')} className={inputClass} required />
          </div>
          <div>
            <label className="block text-sm text-forge-text-dim mb-1">Description</label>
            <textarea value={form.description} onChange={set('description')} className={`${inputClass} h-24 resize-none`} />
          </div>
          <div>
            <label className="block text-sm text-forge-text-dim mb-1">Instructables URL</label>
            <input value={form.instructables_url} onChange={set('instructables_url')} className={inputClass} type="url" placeholder="https://www.instructables.com/..." />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-forge-text-dim mb-1">Category</label>
              <select value={form.category_id} onChange={set('category_id')} className={inputClass}>
                <option value="">None</option>
                {categories.map((c) => <option key={c.id} value={c.id}>{c.icon} {c.name}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm text-forge-text-dim mb-1">Difficulty</label>
              <select value={form.difficulty} onChange={set('difficulty')} className={inputClass}>
                {[1, 2, 3, 4, 5].map((d) => <option key={d} value={d}>{'★'.repeat(d)} ({d})</option>)}
              </select>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-sm text-forge-text-dim mb-1">Bonus ($)</label>
              <input value={form.bonus_amount} onChange={set('bonus_amount')} className={inputClass} type="number" step="0.01" min="0" />
            </div>
            <div>
              <label className="block text-sm text-forge-text-dim mb-1">Materials Budget ($)</label>
              <input value={form.materials_budget} onChange={set('materials_budget')} className={inputClass} type="number" step="0.01" min="0" />
            </div>
            <div>
              <label className="block text-sm text-forge-text-dim mb-1">Due Date</label>
              <input value={form.due_date} onChange={set('due_date')} className={inputClass} type="date" />
            </div>
          </div>

          <button type="submit" className="w-full bg-amber-primary hover:bg-amber-highlight text-black font-semibold py-2.5 rounded-lg transition-colors">
            Create Project
          </button>
        </Card>
      </form>
    </div>
  );
}
