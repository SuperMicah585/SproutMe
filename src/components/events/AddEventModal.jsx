import React, { useEffect, useState } from 'react';
import { useTheme } from '../../context/ThemeContext';
import { useToast } from '../../pages/Components/ToastNotification';
import { trackEvent } from '../../utils/analytics';

const emptyForm = {
  event_name: '',
  date: '',
  time: '',
  venue: '',
  genre: '',
  ticket_info: '',
  organizer: '',
  event_url: '',
};

const formatDisplayDate = (dateValue, timeValue) => {
  const d = new Date(`${dateValue}T${timeValue || '00:00'}`);
  if (Number.isNaN(d.getTime())) return dateValue;
  const weekday = d.toLocaleDateString('en-US', { weekday: 'short' });
  const month = d.toLocaleDateString('en-US', { month: 'short' });
  const day = d.getDate();
  if (!timeValue) return `${weekday}: ${month} ${day}`;
  const time = d
    .toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
    .toLowerCase()
    .replace(' ', '');
  return `${weekday}: ${month} ${day} (${time})`;
};

const AddEventModal = ({ open, onClose, onAdd, apiUrl }) => {
  const { darkMode } = useTheme();
  const toast = useToast();
  const [form, setForm] = useState(emptyForm);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return undefined;
    const onKeyDown = (e) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [open, onClose]);

  if (!open) return null;

  const inputClass = `w-full rounded-md p-2 border ${
    darkMode
      ? 'bg-gray-700 border-gray-600 text-gray-200 placeholder-gray-400'
      : 'bg-white border-gray-300 text-gray-900 placeholder-gray-500'
  }`;

  const handleChange = (field) => (e) => {
    setForm((prev) => ({ ...prev, [field]: e.target.value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.event_name.trim() || !form.date || !form.venue.trim()) {
      toast.error('Please add an event name, date, and venue.');
      return;
    }

    const event = {
      event_name: form.event_name.trim(),
      date: formatDisplayDate(form.date, form.time),
      raw_date: form.date,
      venue: form.venue.trim(),
      genre: form.genre.trim(),
      ticket_info: form.ticket_info.trim() || 'N/A',
      organizer: form.organizer.trim() || 'N/A',
      event_url: form.event_url.trim(),
      is_favorite: false,
      user_submitted: true,
    };

    setSubmitting(true);
    try {
      const response = await fetch(`${apiUrl}/add_event`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(event),
      });

      if (!response.ok) {
        throw new Error(`Server responded with status ${response.status}`);
      }

      trackEvent('add_event', { success: true });
      onAdd(event);
      setForm(emptyForm);
      toast.success('Event added!');
      onClose();
    } catch (error) {
      trackEvent('add_event', { success: false });
      const subject = encodeURIComponent(`New SproutMe event: ${event.event_name}`);
      const body = encodeURIComponent(
        [
          `Event: ${event.event_name}`,
          `Date: ${event.date}`,
          `Venue: ${event.venue}`,
          `Genre: ${event.genre || 'Not specified'}`,
          `Tickets: ${event.ticket_info}`,
          `Organizer: ${event.organizer}`,
          `Link: ${event.event_url || 'None'}`,
        ].join('\n')
      );
      window.location.href = `mailto:micahphlps@gmail.com?subject=${subject}&body=${body}`;
      onAdd(event);
      setForm(emptyForm);
      toast.success('Event added to your list. We also opened an email so we can publish it for everyone.');
      onClose();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-start sm:items-center justify-center p-3 sm:p-4 overflow-y-auto bg-black bg-opacity-60"
      onClick={onClose}
    >
      <form
        role="dialog"
        aria-modal="true"
        aria-labelledby="add-event-title"
        onClick={(e) => e.stopPropagation()}
        onSubmit={handleSubmit}
        className={`w-full max-w-lg my-4 sm:my-8 rounded-xl shadow-2xl border overflow-y-auto ${
          darkMode ? 'bg-gray-800 border-green-600 text-gray-100' : 'bg-white border-green-300 text-gray-900'
        }`}
      >
        <div className={`flex items-center justify-between p-4 border-b ${darkMode ? 'border-gray-700' : 'border-gray-200'}`}>
          <h2 id="add-event-title" className={`text-lg font-bold ${darkMode ? 'text-green-400' : 'text-green-600'}`}>
            Add an event
          </h2>
          <button
            type="button"
            onClick={onClose}
            className={darkMode ? 'text-gray-400 hover:text-gray-200' : 'text-gray-500 hover:text-gray-700'}
            aria-label="Close add event form"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="p-4 space-y-3 overflow-y-auto" style={{ maxHeight: '70vh' }}>
          <label className="block text-sm font-medium">
            Artist / event name *
            <input className={`${inputClass} mt-1`} value={form.event_name} onChange={handleChange('event_name')} required />
          </label>
          <div className="grid grid-cols-2 gap-2">
            <label className="block text-sm font-medium">
              Date *
              <input type="date" className={`${inputClass} mt-1`} value={form.date} onChange={handleChange('date')} required />
            </label>
            <label className="block text-sm font-medium">
              Time
              <input type="time" className={`${inputClass} mt-1`} value={form.time} onChange={handleChange('time')} />
            </label>
          </div>
          <label className="block text-sm font-medium">
            Venue *
            <input className={`${inputClass} mt-1`} value={form.venue} onChange={handleChange('venue')} required />
          </label>
          <label className="block text-sm font-medium">
            Genre
            <input className={`${inputClass} mt-1`} value={form.genre} onChange={handleChange('genre')} placeholder="house, techno..." />
          </label>
          <label className="block text-sm font-medium">
            Tickets
            <input className={`${inputClass} mt-1`} value={form.ticket_info} onChange={handleChange('ticket_info')} placeholder="$20 | 21+" />
          </label>
          <label className="block text-sm font-medium">
            Organizer
            <input className={`${inputClass} mt-1`} value={form.organizer} onChange={handleChange('organizer')} />
          </label>
          <label className="block text-sm font-medium">
            Event link
            <input type="url" className={`${inputClass} mt-1`} value={form.event_url} onChange={handleChange('event_url')} placeholder="https://" />
          </label>
        </div>

        <div className={`p-4 border-t flex justify-end gap-2 ${darkMode ? 'border-gray-700' : 'border-gray-200'}`}>
          <button
            type="button"
            onClick={onClose}
            className={`px-4 py-2 rounded-lg text-sm font-medium ${
              darkMode ? 'bg-gray-700 hover:bg-gray-600 text-gray-200' : 'bg-gray-200 hover:bg-gray-300 text-gray-700'
            }`}
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting}
            className={`${
              darkMode ? 'bg-green-700 hover:bg-green-600' : 'bg-green-600 hover:bg-green-500'
            } text-white px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-60`}
          >
            {submitting ? 'Adding...' : 'Add event'}
          </button>
        </div>
      </form>
    </div>
  );
};

export default AddEventModal;
