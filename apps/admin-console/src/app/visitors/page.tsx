import { redirect } from 'next/navigation';

export default function VisitorsRedirect() {
  redirect('/admin/visitors');
}
