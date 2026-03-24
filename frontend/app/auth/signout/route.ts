import { createClient } from '@/lib/supabase/server'
import { revalidatePath } from 'next/cache'
import { redirect } from 'next/navigation'
import { type NextRequest } from 'next/server'

export async function POST(request: NextRequest) {
  const supabase = await createClient()

  // Check if a user's session exists
  const {
    data: { user },
  } = await supabase.auth.getUser()

  if (user) {
    await supabase.auth.signOut()
  }

  revalidatePath('/', 'layout')
  return redirect('/login')
}
