import { redirect } from "next/navigation";

// La raíz redirige al dashboard (o al login si no está autenticado)
export default function Home() {
  redirect("/dashboard");
}
