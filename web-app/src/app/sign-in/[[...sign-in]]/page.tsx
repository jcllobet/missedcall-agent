import { SignIn } from "@clerk/nextjs";

export default function Page() {
  return (
    <main className="flex min-h-[calc(100vh-4rem)] items-center justify-center px-5 py-12">
      <SignIn />
    </main>
  );
}
