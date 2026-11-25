import AdviserProfile from "@/components/explore/AdviserProfile";

export default async function AdviserRoute({ params }: { params: Promise<{ crd: string }> }) {
  const { crd } = await params;
  return <AdviserProfile key={crd} crd={crd} />;
}
