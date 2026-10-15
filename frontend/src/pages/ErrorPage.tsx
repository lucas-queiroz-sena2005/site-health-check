import { Link, useRouteError, isRouteErrorResponse } from 'react-router-dom'
import { Button } from '@/components/ui/button'

export function ErrorPage() {
  const error = useRouteError()

  let title = 'Something went wrong'
  let description = 'An unexpected error occurred while loading this page.'

  if (isRouteErrorResponse(error)) {
    if (error.status === 404) {
      title = 'Page Not Found'
      description = "The page you're looking for does not exist or has been moved."
    } else {
      title = `Error ${error.status}`
      description = error.statusText || description
    }
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] px-4 text-center">
      <h1 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">
        {title}
      </h1>
      <p className="mt-3 text-base text-muted-foreground max-w-md">
        {description}
      </p>
      <div className="mt-6 flex gap-3">
        <Link to="/">
          <Button variant="default" className="font-semibold">
            Back to Dashboard
          </Button>
        </Link>
        <Link to="/scheduled-runs">
          <Button variant="outline" className="font-semibold">
            Scheduled Scans
          </Button>
        </Link>
      </div>
    </div>
  )
}
