import SecurityPage from "@/components/explore/SecurityPage";

export default async function SecurityRoute({ params }: { params: Promise<{ identifier: string }> }) {
  const { identifier } = await params;
  return <SecurityPage key={identifier} identifier={identifier} />;
}
