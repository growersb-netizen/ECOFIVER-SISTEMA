/**
 * Root redirect — manda al login (o al dashboard si ya hay sesión).
 */
import { redirect } from "next/navigation";

export default function AdminHome() {
  redirect("/login");
}
