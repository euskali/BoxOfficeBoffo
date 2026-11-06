export default function SectionBar({ children }: { children: string }) {
  return (
    <div className="bar mb-2 text-body">
      <span aria-hidden="true">» </span>
      {children}
    </div>
  )
}
